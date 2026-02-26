# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
# Licensed to Elasticsearch B.V. under one or more contributor
# license agreements. See the NOTICE file distributed with
# this work for additional information regarding copyright
# ownership. Elasticsearch B.V. licenses this file to you under
# the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#	http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import asyncio
import contextvars
import json
import logging
import random
import re
import sys
import time
import types
from collections import Counter, OrderedDict
from copy import deepcopy
from enum import Enum
from functools import total_ordering
from io import BytesIO
from os.path import commonprefix
import multiprocessing
from typing import Any, Dict, List, Optional

import ijson

from osbenchmark.exceptions import BenchmarkConnectionTimeout as ConnectionTimeout
from osbenchmark.exceptions import BenchmarkNotFoundError as NotFoundError

from osbenchmark import exceptions, workload
from osbenchmark.utils import convert
from osbenchmark.client import RequestContextHolder
# Mapping from operation type to specific runner
from osbenchmark.utils.parse import parse_int_parameter, parse_string_parameter, parse_float_parameter
from osbenchmark.solr import runner as solr_runner

__RUNNERS = {}


def register_default_runners():
    # Engine-agnostic operations
    register_runner(workload.OperationType.Sleep, Sleep(), async_runner=True)
    register_runner(workload.OperationType.RawRequest, RawRequest(), async_runner=True)
    register_runner(workload.OperationType.Composite, Composite(), async_runner=True)
    # Backup operations (TODO: port to Solr backup API)
    register_runner(workload.OperationType.CreateBackup, CreateBackup(), async_runner=True)
    register_runner(workload.OperationType.RestoreBackup, RestoreBackup(), async_runner=True)
    register_runner(workload.OperationType.DeleteBackupRepository, Retry(DeleteBackupRepository()), async_runner=True)
    register_runner(workload.OperationType.CreateBackupRepository, Retry(CreateBackupRepository()), async_runner=True)
    register_runner(workload.OperationType.WaitForBackupCreate, Retry(WaitForBackupCreate()), async_runner=True)
    # Solr-native runners
    solr_runner.register_solr_runners(register_runner)

def runner_for(operation_type):
    try:
        return __RUNNERS[operation_type]
    except KeyError:
        raise exceptions.BenchmarkError("No runner available for operation type [%s]" % operation_type)


def enable_assertions(enabled):
    """
    Changes whether assertions are enabled. The status changes for all tasks that are executed after this call.

    :param enabled: ``True`` to enable assertions, ``False`` to disable them.
    """
    AssertingRunner.assertions_enabled = enabled


def register_runner(operation_type, runner, **kwargs):
    logger = logging.getLogger(__name__)
    async_runner = kwargs.get("async_runner", False)
    if isinstance(operation_type, workload.OperationType):
        operation_type = operation_type.to_hyphenated_string()

    if not async_runner:
        raise exceptions.BenchmarkAssertionError(
            "Runner [{}] must be implemented as async runner and registered with async_runner=True.".format(str(runner)))

    if getattr(runner, "multi_cluster", False):
        if "__aenter__" in dir(runner) and "__aexit__" in dir(runner):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Registering runner object [%s] for [%s].", str(runner), str(operation_type))
            cluster_aware_runner = _multi_cluster_runner(runner, str(runner), context_manager_enabled=True)
        else:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Registering context-manager capable runner object [%s] for [%s].", str(runner), str(operation_type))
            cluster_aware_runner = _multi_cluster_runner(runner, str(runner))
    # we'd rather use callable() but this will erroneously also classify a class as callable...
    elif isinstance(runner, types.FunctionType):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Registering runner function [%s] for [%s].", str(runner), str(operation_type))
        cluster_aware_runner = _single_cluster_runner(runner, runner.__name__)
    elif "__aenter__" in dir(runner) and "__aexit__" in dir(runner):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Registering context-manager capable runner object [%s] for [%s].", str(runner), str(operation_type))
        cluster_aware_runner = _single_cluster_runner(runner, str(runner), context_manager_enabled=True)
    else:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Registering runner object [%s] for [%s].", str(runner), str(operation_type))
        cluster_aware_runner = _single_cluster_runner(runner, str(runner))

    __RUNNERS[operation_type] = _with_completion(_with_assertions(cluster_aware_runner))

# Only intended for unit-testing!
def remove_runner(operation_type):
    del __RUNNERS[operation_type]


class Runner:
    """
    Base class for all operations against a search cluster.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    async def __aenter__(self):
        return self

    async def __call__(self, client, params):
        """
        Runs the actual method that should be benchmarked.

        :param args: All arguments that are needed to call this method.
        :return: A pair of (int, String). The first component indicates the "weight" of this call. it is typically 1 but for bulk operations
                 it should be the actual bulk size. The second component is the "unit" of weight which should be "ops" (short for
                 "operations") by default. If applicable, the unit should always be in plural form. It is used in metrics records
                 for throughput and results. A value will then be shown as e.g. "111 ops/s".
        """
        raise NotImplementedError("abstract operation")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    def _default_kw_params(self, params):
        # map of API kwargs to OSB config parameters
        kw_dict = {
            "body": "body",
            "headers": "headers",
            "index": "index",
            "opaque_id": "opaque-id",
            "params": "request-params",
            "request_timeout": "request-timeout",
        }
        full_result =  {k: params.get(v) for (k, v) in kw_dict.items()}
        # filter Nones
        return dict(filter(lambda kv: kv[1] is not None, full_result.items()))

    def _transport_request_params(self, params):
        request_params = params.get("request-params", {})
        request_timeout = params.get("request-timeout")
        if request_timeout is not None:
            request_params["request_timeout"] = request_timeout
        headers = params.get("headers") or {}
        opaque_id = params.get("opaque-id")
        if opaque_id is not None:
            headers.update({"x-opaque-id": opaque_id})
        return request_params, headers

request_context_holder = RequestContextHolder()

def time_func(func):
    async def advised(*args, **kwargs):
        request_context_holder.on_client_request_start()
        try:
            response = await func(*args, **kwargs)
            return response
        finally:
            request_context_holder.on_client_request_end()
    return advised


class Delegator:
    """
    Mixin to unify delegate handling
    """
    def __init__(self, delegate, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delegate = delegate


def unwrap(runner):
    """
    Unwraps all delegators until the actual runner.

    :param runner: An arbitrarily nested chain of delegators around a runner.
    :return: The innermost runner.
    """
    delegate = getattr(runner, "delegate", None)
    if delegate:
        return unwrap(delegate)
    else:
        return runner


def _single_cluster_runner(runnable, name, context_manager_enabled=False):
    # only pass the default ES client
    return MultiClientRunner(runnable, name, lambda client: client["default"], context_manager_enabled)


def _multi_cluster_runner(runnable, name, context_manager_enabled=False):
    # pass all ES clients
    return MultiClientRunner(runnable, name, lambda client: client, context_manager_enabled)


def _with_assertions(delegate):
    return AssertingRunner(delegate)


def _with_completion(delegate):
    unwrapped_runner = unwrap(delegate)
    if hasattr(unwrapped_runner, "completed") and hasattr(unwrapped_runner, "task_progress"):
        return WithCompletion(delegate, unwrapped_runner)
    else:
        return NoCompletion(delegate)


class NoCompletion(Runner, Delegator):
    def __init__(self, delegate):
        super().__init__(delegate=delegate)

    @property
    def completed(self):
        return None

    @property
    def task_progress(self):
        return None

    async def __call__(self, *args):
        return await self.delegate(*args)

    def __repr__(self, *args, **kwargs):
        return repr(self.delegate)

    async def __aenter__(self):
        await self.delegate.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)


class WithCompletion(Runner, Delegator):
    def __init__(self, delegate, progressable):
        super().__init__(delegate=delegate)
        self.progressable = progressable

    @property
    def completed(self):
        return self.progressable.completed

    @property
    def task_progress(self):
        return self.progressable.task_progress

    async def __call__(self, *args):
        return await self.delegate(*args)

    def __repr__(self, *args, **kwargs):
        return repr(self.delegate)

    async def __aenter__(self):
        await self.delegate.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)


class MultiClientRunner(Runner, Delegator):
    def __init__(self, runnable, name, client_extractor, context_manager_enabled=False):
        super().__init__(delegate=runnable)
        self.name = name
        self.client_extractor = client_extractor
        self.context_manager_enabled = context_manager_enabled

    async def __call__(self, *args):
        return await self.delegate(self.client_extractor(args[0]), *args[1:])

    def __repr__(self, *args, **kwargs):
        if self.context_manager_enabled:
            return "user-defined context-manager enabled runner for [%s]" % self.name
        else:
            return "user-defined runner for [%s]" % self.name

    async def __aenter__(self):
        if self.context_manager_enabled:
            await self.delegate.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context_manager_enabled:
            return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)
        else:
            return False


class AssertingRunner(Runner, Delegator):
    assertions_enabled = False

    def __init__(self, delegate):
        super().__init__(delegate=delegate)
        self.predicates = {
            ">": self.greater_than,
            ">=": self.greater_than_or_equal,
            "<": self.smaller_than,
            "<=": self.smaller_than_or_equal,
            "==": self.equal,
        }

    def greater_than(self, expected, actual):
        return actual > expected

    def greater_than_or_equal(self, expected, actual):
        return actual >= expected

    def smaller_than(self, expected, actual):
        return actual < expected

    def smaller_than_or_equal(self, expected, actual):
        return actual <= expected

    def equal(self, expected, actual):
        return actual == expected

    def check_assertion(self, op_name, assertion, properties):
        path = assertion["property"]
        predicate_name = assertion["condition"]
        expected_value = assertion["value"]
        actual_value = properties
        for k in path.split("."):
            actual_value = actual_value[k]
        predicate = self.predicates[predicate_name]
        success = predicate(expected_value, actual_value)
        if not success:
            if op_name:
                msg = f"Expected [{path}] in [{op_name}] to be {predicate_name} [{expected_value}] but was [{actual_value}]."
            else:
                msg = f"Expected [{path}] to be {predicate_name} [{expected_value}] but was [{actual_value}]."

            raise exceptions.BenchmarkTaskAssertionError(msg)

    async def __call__(self, *args):
        params = args[1]
        return_value = await self.delegate(*args)
        if AssertingRunner.assertions_enabled and "assertions" in params:
            op_name = params.get("name")
            if isinstance(return_value, dict):
                for assertion in params["assertions"]:
                    self.check_assertion(op_name, assertion, return_value)
            else:
                self.logger.debug("Skipping assertion check in [%s] as [%s] does not return a dict.",
                                  op_name, repr(self.delegate))
        return return_value

    def __repr__(self, *args, **kwargs):
        return repr(self.delegate)

    async def __aenter__(self):
        await self.delegate.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)


def mandatory(params, key, op):
    try:
        return params[key]
    except KeyError:
        raise exceptions.DataError(
            f"Parameter source for operation '{str(op)}' did not provide the mandatory parameter '{key}'. "
            f"Add it to your parameter source and try again.")


# TODO: remove and use https://docs.python.org/3/library/stdtypes.html#str.removeprefix
#  once Python 3.9 becomes the minimum version
def remove_prefix(string, prefix):
    if string.startswith(prefix):
        return string[len(prefix):]
    return string


def escape(v):
    """
    Escapes values so they can be used as query parameters

    :param v: The raw value. May be None.
    :return: The escaped value.
    """
    if v is None:
        return None
    elif isinstance(v, bool):
        return str(v).lower()
    else:
        return str(v)


def parse(text: BytesIO, props: List[str], lists: List[str] = None) -> dict:
    """
    Selectively parse the provided text as JSON extracting only the properties provided in ``props``. If ``lists`` is
    specified, this function determines whether the provided lists are empty (respective value will be ``True``) or
    contain elements (respective key will be ``False``).

    :param text: A text to parse.
    :param props: A mandatory list of property paths (separated by a dot character) for which to extract values.
    :param lists: An optional list of property paths to JSON lists in the provided text.
    :return: A dict containing all properties and lists that have been found in the provided text.
    """
    text.seek(0)
    parser = ijson.parse(text)
    parsed = {}
    parsed_lists = {}
    current_list = None
    expect_end_array = False
    try:
        for prefix, event, value in parser:
            if expect_end_array:
                # True if the list is empty, False otherwise
                parsed_lists[current_list] = event == "end_array"
                expect_end_array = False
            if prefix in props:
                parsed[prefix] = value
            elif lists is not None and prefix in lists and event == "start_array":
                current_list = prefix
                expect_end_array = True
            # found all necessary properties
            if len(parsed) == len(props) and (lists is None or len(parsed_lists) == len(lists)):
                break
    except ijson.IncompleteJSONError:
        # did not find all properties
        pass

    parsed.update(parsed_lists)
    return parsed


class RawRequest(Runner):
    async def __call__(self, client, params):
        request_params, headers = self._transport_request_params(params)
        if "ignore" in params:
            request_params["ignore"] = params["ignore"]
        path = mandatory(params, "path", self)
        if not path.startswith("/"):
            self.logger.error("RawRequest failed. Path parameter: [%s] must begin with a '/'.", path)
            raise exceptions.BenchmarkAssertionError(f"RawRequest [{path}] failed. Path parameter must begin with a '/'.")
        if not bool(headers):
            #counter-intuitive, but preserves prior behavior
            headers = None

        request_context_holder.on_client_request_start()
        await client.transport.perform_request(method=params.get("method", "GET"),
                                           url=path,
                                           headers=headers,
                                           body=params.get("body"),
                                           params=request_params)
        request_context_holder.on_client_request_end()

    def __repr__(self, *args, **kwargs):
        return "raw-request"


class Sleep(Runner):
    """
    Sleeps for the specified duration not issuing any request.
    """
    @time_func
    async def __call__(self, client, params):
        sleep_duration = mandatory(params, "duration", "sleep")
        client.on_request_start()
        try:
            await asyncio.sleep(sleep_duration)
        finally:
            client.on_request_end()

    def __repr__(self, *args, **kwargs):
        return "sleep"


class DeleteBackupRepository(Runner):
    # TODO: Port to Solr — implement using Solr backup/restore V2 API:
    #   POST /api/collections/{collection}/backups/{name}/versions
    #   Docs: https://solr.apache.org/guide/solr/latest/configuration-guide/backups.html
    #   Current implementation is OpenSearch-specific and will fail against Solr.
    """
    Deletes a snapshot repository
    """
    @time_func
    async def __call__(self, client, params):
        await client.snapshot.delete_repository(repository=mandatory(params, "repository", repr(self)))

    def __repr__(self, *args, **kwargs):
        return "delete-snapshot-repository"


class CreateBackupRepository(Runner):
    # TODO: Port to Solr — implement using Solr backup/restore V2 API:
    #   POST /api/collections/{collection}/backups/{name}/versions
    #   Docs: https://solr.apache.org/guide/solr/latest/configuration-guide/backups.html
    #   Current implementation is OpenSearch-specific and will fail against Solr.
    """
    Creates a new snapshot repository
    """
    @time_func
    async def __call__(self, client, params):
        request_params = params.get("request-params", {})
        await client.snapshot.create_repository(repository=mandatory(params, "repository", repr(self)),
                                            body=mandatory(params, "body", repr(self)),
                                            params=request_params)

    def __repr__(self, *args, **kwargs):
        return "create-snapshot-repository"


class CreateBackup(Runner):
    # TODO: Port to Solr — implement using Solr backup/restore V2 API:
    #   POST /api/collections/{collection}/backups/{name}/versions
    #   Docs: https://solr.apache.org/guide/solr/latest/configuration-guide/backups.html
    #   Current implementation is OpenSearch-specific and will fail against Solr.
    """
    Creates a new snapshot repository
    """
    @time_func
    async def __call__(self, client, params):
        wait_for_completion = params.get("wait-for-completion", False)
        repository = mandatory(params, "repository", repr(self))
        snapshot = mandatory(params, "snapshot", repr(self))
        # just assert, gets set in _default_kw_params
        mandatory(params, "body", repr(self))
        api_kwargs = self._default_kw_params(params)
        await client.snapshot.create(repository=repository,
                                 snapshot=snapshot,
                                 wait_for_completion=wait_for_completion,
                                 **api_kwargs)

    def __repr__(self, *args, **kwargs):
        return "create-snapshot"


class WaitForBackupCreate(Runner):
    # TODO: Port to Solr — implement using Solr backup/restore V2 API:
    #   POST /api/collections/{collection}/backups/{name}/versions
    #   Docs: https://solr.apache.org/guide/solr/latest/configuration-guide/backups.html
    #   Current implementation is OpenSearch-specific and will fail against Solr.
    async def __call__(self, client, params):
        repository = mandatory(params, "repository", repr(self))
        snapshot = mandatory(params, "snapshot", repr(self))
        wait_period = params.get("completion-recheck-wait-period", 1)

        snapshot_done = False
        stats = {}

        while not snapshot_done:
            response = await client.snapshot.status(repository=repository,
                                                snapshot=snapshot,
                                                ignore_unavailable=True)

            if "snapshots" in response:
                response_state = response["snapshots"][0]["state"]
                if response_state == "FAILED":
                    self.logger.error("Snapshot [%s] failed. Response:\n%s", snapshot, json.dumps(response, indent=2))
                    raise exceptions.BenchmarkAssertionError(f"Snapshot [{snapshot}] failed. Please check logs.")
                snapshot_done = response_state == "SUCCESS"
                stats = response["snapshots"][0]["stats"]

            if not snapshot_done:
                await asyncio.sleep(wait_period)

        size = stats["total"]["size_in_bytes"]
        file_count = stats["total"]["file_count"]
        start_time_in_millis = stats["start_time_in_millis"]
        duration_in_millis = stats["time_in_millis"]
        duration_in_seconds = duration_in_millis / 1000

        return {
            "weight": size,
            "unit": "byte",
            "success": True,
            "throughput": size / duration_in_seconds,
            "start_time_millis": start_time_in_millis,
            "stop_time_millis": start_time_in_millis + duration_in_millis,
            "duration": duration_in_millis,
            "file_count": file_count
        }

    def __repr__(self, *args, **kwargs):
        return "wait-for-snapshot-create"


class RestoreBackup(Runner):
    # TODO: Port to Solr — implement using Solr backup/restore V2 API:
    #   POST /api/collections/{collection}/backups/{name}/versions
    #   Docs: https://solr.apache.org/guide/solr/latest/configuration-guide/backups.html
    #   Current implementation is OpenSearch-specific and will fail against Solr.
    """
    Restores a snapshot from an already registered repository
    """
    @time_func
    async def __call__(self, client, params):
        api_kwargs = self._default_kw_params(params)
        await client.snapshot.restore(repository=mandatory(params, "repository", repr(self)),
                                  snapshot=mandatory(params, "snapshot", repr(self)),
                                  wait_for_completion=params.get("wait-for-completion", False),
                                  **api_kwargs)

    def __repr__(self, *args, **kwargs):
        return "restore-snapshot"


def async_search_ids(op_names):
    subjects = [op_names] if isinstance(op_names, str) else op_names
    for subject in subjects:
        subject_id = CompositeContext.get(subject)
        # skip empty ids, searches have already completed
        if subject_id:
            yield subject_id, subject


class CompositeContext:
    ctx = contextvars.ContextVar("composite_context")

    def __init__(self):
        self.token = None

    async def __aenter__(self):
        self.token = CompositeContext.ctx.set({})
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        CompositeContext.ctx.reset(self.token)
        return False

    @staticmethod
    def put(key, value):
        CompositeContext._ctx()[key] = value

    @staticmethod
    def get(key):
        try:
            return CompositeContext._ctx()[key]
        except KeyError:
            raise KeyError(f"Unknown property [{key}]. Currently recognized "
                           f"properties are [{', '.join(CompositeContext._ctx().keys())}].") from None

    @staticmethod
    def remove(key):
        try:
            CompositeContext._ctx().pop(key)
        except KeyError:
            raise KeyError(f"Unknown property [{key}]. Currently recognized "
                           f"properties are [{', '.join(CompositeContext._ctx().keys())}].") from None

    @staticmethod
    def _ctx():
        try:
            return CompositeContext.ctx.get()
        except LookupError:
            raise exceptions.BenchmarkAssertionError("This operation is only allowed inside a composite operation.") from None


class Composite(Runner):
    """
    Executes a complex request structure which is measured by OSB as one composite operation.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supported_op_types = [
            "create-point-in-time",
            "delete-point-in-time",
            "list-all-point-in-time",
            "search",
            "paginated-search",
            "raw-request",
            "sleep",
            "submit-async-search",
            "get-async-search",
            "delete-async-search"
        ]

    async def run_stream(self, client, stream, connection_limit):
        streams = []
        timings = []
        try:
            for item in stream:
                if "stream" in item:
                    streams.append(asyncio.create_task(self.run_stream(client, item["stream"], connection_limit)))
                elif "operation-type" in item:
                    # consume all prior streams first
                    if streams:
                        streams_timings = await asyncio.gather(*streams)
                        for stream_timings in streams_timings:
                            timings += stream_timings
                        streams = []
                    op_type = item["operation-type"]
                    if op_type not in self.supported_op_types:
                        raise exceptions.BenchmarkAssertionError(
                            f"Unsupported operation-type [{op_type}]. Use one of [{', '.join(self.supported_op_types)}].")
                    runner = RequestTiming(runner_for(op_type))
                    async with connection_limit:
                        async with runner:
                            response = await runner({"default": client}, item)
                            timing = response.get("dependent_timing") if response else None
                            if timing:
                                timings.append(timing)

                else:
                    raise exceptions.BenchmarkAssertionError("Requests structure must contain [stream] or [operation-type].")
        except BaseException:
            # stop all already created tasks in case of exceptions
            for s in streams:
                if not s.done():
                    s.cancel()
            raise

        # complete any outstanding streams
        if streams:
            streams_timings = await asyncio.gather(*streams)
            for stream_timings in streams_timings:
                timings += stream_timings
        return timings

    async def __call__(self, client, params):
        requests = mandatory(params, "requests", self)
        max_connections = params.get("max-connections", sys.maxsize)
        async with CompositeContext():
            response = await self.run_stream(client, requests, asyncio.BoundedSemaphore(max_connections))
        return {
            "weight": 1,
            "unit": "ops",
            "dependent_timing": response
        }

    def __repr__(self, *args, **kwargs):
        return "composite"


class RequestTiming(Runner, Delegator):
    def __init__(self, delegate):
        super().__init__(delegate=delegate)

    async def __aenter__(self):
        await self.delegate.__aenter__()
        return self

    async def __call__(self, client, params):
        absolute_time = time.time()
        async with client["default"].new_request_context() as request_context:
            return_value = await self.delegate(client, params)
            if isinstance(return_value, tuple) and len(return_value) == 2:
                total_ops, total_ops_unit = return_value
                result = {
                    "weight": total_ops,
                    "unit": total_ops_unit,
                    "success": True
                }
            elif isinstance(return_value, dict):
                result = return_value
            else:
                result = {
                    "weight": 1,
                    "unit": "ops",
                    "success": True
                }

            start = request_context.request_start
            end = request_context.request_end
            result["dependent_timing"] = {
                "operation": params.get("name"),
                "operation-type": params.get("operation-type"),
                "absolute_time": absolute_time,
                "request_start": start,
                "request_end": end,
                "service_time": end - start
            }
        return result

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)


# TODO: Allow to use this from (selected) regular runners and add user documentation.
# TODO: It would maybe be interesting to add meta-data on how many retries there were.
class Retry(Runner, Delegator):
    """
    This runner can be used as a wrapper around regular runners to retry operations.

    It defines the following parameters:

    * ``retries`` (optional, default 0): The number of times the operation is retried.
    * ``retry-until-success`` (optional, default False): Retries until the delegate returns a success. This will also
                              forcibly set ``retry-on-error`` to ``True``.
    * ``retry-wait-period`` (optional, default 0.5): The time in seconds to wait after an error.
    * ``retry-on-timeout`` (optional, default True): Whether to retry on connection timeout.
    * ``retry-on-error`` (optional, default False): Whether to retry on failure (i.e. the delegate
                         returns ``success == False``)
    """

    def __init__(self, delegate, retry_until_success=False):
        super().__init__(delegate=delegate)
        self.retry_until_success = retry_until_success

    async def __aenter__(self):
        await self.delegate.__aenter__()
        return self

    async def __call__(self, client, params):
        # pylint: disable=import-outside-toplevel
        import socket
        retry_until_success = params.get("retry-until-success", self.retry_until_success)
        if retry_until_success:
            max_attempts = sys.maxsize
            retry_on_error = True
        else:
            max_attempts = params.get("retries", 0) + 1
            retry_on_error = params.get("retry-on-error", False)
        sleep_time = params.get("retry-wait-period", 0.5)
        retry_on_timeout = params.get("retry-on-timeout", True)

        for attempt in range(max_attempts):
            last_attempt = attempt + 1 == max_attempts
            try:
                return_value = await self.delegate(client, params)
                if last_attempt or not retry_on_error:
                    return return_value
                # we can determine success if and only if the runner returns a dict. Otherwise, we have to assume it was fine.
                elif isinstance(return_value, dict):
                    if return_value.get("success", True):
                        self.logger.debug("%s has returned successfully", repr(self.delegate))
                        return return_value
                    else:
                        self.logger.info("[%s] has returned with an error: %s. Retrying in [%.2f] seconds.",
                                         repr(self.delegate), return_value, sleep_time)
                        await asyncio.sleep(sleep_time)
                else:
                    return return_value
            except Exception as e:
                if isinstance(e, (socket.timeout, exceptions.BenchmarkConnectionError)):
                    if last_attempt or not retry_on_timeout:
                        raise e
                    else:
                        await asyncio.sleep(sleep_time)
                elif isinstance(e, exceptions.BenchmarkTransportError):
                    if last_attempt or not retry_on_timeout:
                        raise e
                    elif e.status_code == 408:
                        self.logger.info("[%s] has timed out. Retrying in [%.2f] seconds.", repr(self.delegate), sleep_time)
                        await asyncio.sleep(sleep_time)
                    else:
                        raise e
                else:
                    raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.delegate.__aexit__(exc_type, exc_val, exc_tb)

    def __repr__(self, *args, **kwargs):
        return "retryable %s" % repr(self.delegate)
