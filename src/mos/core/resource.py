import abc


class Resource(abc.ABC):
    """Base class for plugin-managed resources (e.g., Grafana dashboards).

    A resource is a piece of state the plugin owns in an external
    system. Subclasses declare what they are via :attr:`name` and how
    to deploy / remove them via :meth:`install` / :meth:`uninstall`.

    The three methods form the minimal contract. Additional state
    (e.g. ``status()``, ``update()``) is welcome but not required.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Stable identifier used as the resource's UID / key in the
        external system. Must be unique within a plugin."""

    @abc.abstractmethod
    def install(self) -> None:
        """Deploy or register this resource in its target system.

        Implementations should be idempotent: calling ``install()``
        twice on the same resource leaves the system in the same
        state (i.e. the second call is a no-op or an update).
        """

    @abc.abstractmethod
    def uninstall(self) -> None:
        """Remove this resource. Should be a no-op if already absent."""
