import logging

from osbenchmark.builder.utils.jdk_resolver import JdkResolver
from osbenchmark.exceptions import SystemSetupError


class JavaHomeResolver:
    def __init__(self, executor):
        self.logger = logging.getLogger(__name__)
        self.executor = executor
        self.jdk_resolver = JdkResolver(executor)

    def resolve_java_home(self, host, cluster_config):
        runtime_jdks = cluster_config.variables["system"]["runtime"]["jdk"]["version"]

        try:
            allowed_runtime_jdks = [int(v) for v in runtime_jdks.split(",")]
        except ValueError:
            raise SystemSetupError(f"ClusterConfigInstance variable key \"runtime.jdk\" is invalid: \"{runtime_jdks}\" (must be int)")

        self.logger.info("Allowed JDK versions are %s.", allowed_runtime_jdks)
        return self._detect_jdk(host, allowed_runtime_jdks)

    def _detect_jdk(self, host, jdks):
        major, java_home = self.jdk_resolver.resolve_jdk_path(host, jdks)
        self.logger.info("Detected JDK with major version [%s] in [%s].", major, java_home)
        return major, java_home
