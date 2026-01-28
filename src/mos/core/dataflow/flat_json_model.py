"""Concrete :class:`DataModel` implementations.

Currently hosts :class:`FlatJsonDataModel` — flattens nested JSON into a
flat list of ``(dotted_path, value)`` ``DataPoint``s.
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple

from mos.core.dataflow.types import DataModel, DataPoint


class FlatJsonDataModel(DataModel):
    """Flatten nested JSON objects into a stream of ``DataPoint``s.

    Input rules (from the class docstring):
      * Input is a JSON string or an already-parsed Python value.
      * Expected shape: a list of objects, or a single object (auto-wrapped
        into a one-element list).
      * For each object, nested structure is flattened:
          - Nested dict keys are joined with ``.``
          - Arrays of dicts are indexed with ``[i]`` and recursed into
          - **Pure arrays (primitives / mixed) are kept as a single value**
            at the current path — they are not expanded element-by-element

    Each leaf value becomes one :class:`DataPoint`:
      - ``typename`` comes from the model's ``__typename__``
      - ``meta`` is ``{"path": <dotted>path>}`` so downstream consumers
        can still address the original location
      - ``value`` is the leaf value (or a pure array kept whole)

    Subclasses declare ``__fields__``: a ``{flat_path: type}`` mapping
    that drives post-flatten type coercion. After flattening, each leaf
    is passed through ``type(value)`` if its path appears in
    ``__fields__``. Paths not in ``__fields__`` keep their raw value.
    """

    __typename__ = "flat_json"
    __tags__ = {"format": "json", "shape": "flat"}
    __fields__ = {}

    def process(self, data: Any) -> List[DataPoint]:
        """Parse ``data`` (if string), normalize to list, flatten, return DataPoints.

        The returned list is passed through :meth:`post_process` before
        being handed back, so subclasses that override ``post_process``
        get their last-mile transforms for free.
        """
        parsed = self._parse(data)
        items = self._ensure_list(parsed)

        fields = self.__fields__
        result: list[DataPoint] = []
        for item in items:
            for path, value in _flatten(item):
                value = self._coerce(value, fields.get(path))
                result.append(
                    DataPoint(
                        typename=self.typename,
                        meta={"path": path},
                        value=value,
                    )
                )
        return self.post_process(result)

    def post_process(self, data: List[DataPoint]) -> List[DataPoint]:
        """No-op default. Subclasses can override for last-mile transforms."""
        return data

    @staticmethod
    def _coerce(value: Any, target_type: type | None) -> Any:
        """Convert ``value`` to ``target_type`` if it isn't already.

        Returns ``value`` unchanged when ``target_type`` is ``None``
        (path not in ``__fields__``) or when ``value`` is already an
        instance of ``target_type`` (avoids re-converting booleans,
        which are also ``int``, and similar gotchas).

        On conversion failure, raises :class:`TypeError` with the field
        path not directly available — call sites that need field context
        should wrap this in their own try/except or use a custom
        ``__fields__`` resolver.
        """
        if target_type is None or isinstance(value, target_type):
            return value
        try:
            return target_type(value)
        except (TypeError, ValueError) as e:
            raise TypeError(
                f"Cannot coerce value {value!r} to {target_type.__name__}"
            ) from e

    @staticmethod
    def _parse(data: Any) -> Any:
        if isinstance(data, str):
            return json.loads(data)
        return data

    @staticmethod
    def _ensure_list(parsed: Any) -> List[Any]:
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
        raise ValueError(
            f"FlatJsonDataModel expected a dict or list, got {type(parsed).__name__}"
        )


def _flatten(obj: Any, prefix: str = "") -> List[Tuple[str, Any]]:
    """Walk a nested structure, yielding ``(dotted_path, leaf)`` pairs.

    Flattening rules (must match the class docstring):
      - ``dict``: recurse; keys joined with ``.`` (root keys are bare)
      - ``list`` of dicts: index with ``[i]``; recurse into each element
      - ``list`` of anything else (primitives, mixed, empty): kept as a
        single value at the current prefix — pure arrays are not expanded
      - primitive / ``None``: leaf at the current prefix
    """
    if isinstance(obj, dict):
        leaves: List[Tuple[str, Any]] = []
        for key, value in obj.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.extend(_flatten(value, child_prefix))
        return leaves

    if isinstance(obj, list):
        # Only expand arrays whose elements are all dicts.
        if obj and all(isinstance(item, dict) for item in obj):
            leaves = []
            for i, item in enumerate(obj):
                child_prefix = f"{prefix}[{i}]"
                leaves.extend(_flatten(item, child_prefix))
            return leaves
        # Pure / empty / mixed array: keep whole at the current prefix.
        return [(prefix, obj)]

    # Primitive / None: leaf.
    return [(prefix, obj)]
