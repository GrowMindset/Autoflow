import re

from typing import Any


class MergeRunner:
    """
    n8n-like merge node behavior with backward compatibility.

    Config shape:
    {
        "mode": (
            "append" |
            "combine" |
            "combine_by_position" |
            "combine_by_fields" |
            "choose_branch" |
            "choose_input_1" |
            "choose_input_2" |
            "combine" |          # legacy
            "passthrough"        # legacy alias of choose_input_1
        ),
        "output_key": "merged",
        "join_type": "inner" | "left" | "right" | "outer",
        "input_count": 2,
        "choose_branch": "input1",
        "input_1_handle": "input1",
        "input_2_handle": "input2",
        "input_1_field": "",
        "input_2_field": "",
        "allow_missing_branch_fallback": false
    }
    """

    def run(self, config: dict, input_data: list, context: dict[str, Any] = None) -> dict:
        if not isinstance(input_data, list):
            raise ValueError(
                "MergeRunner: input_data must be a list of branch outputs. "
                f"Got {type(input_data).__name__} instead. "
                "Make sure DAG executor is passing all branch outputs as a list."
            )

        if len(input_data) == 0:
            raise ValueError(
                "MergeRunner: input_data is empty. "
                "No branch outputs were collected to merge."
            )

        valid_inputs = [item for item in input_data if item is not None]

        if len(valid_inputs) == 0:
            raise ValueError(
                "MergeRunner: All branch outputs are None. "
                "Nothing to merge."
            )

        cfg = config or {}
        mode = self._normalize_mode(str(cfg.get("mode") or "append"))
        output_key = str((config or {}).get("output_key") or "merged").strip() or "merged"
        join_type = str(cfg.get("join_type") or "inner").strip().lower()
        choose_branch = self._canonical_handle(cfg.get("choose_branch") or "input1")
        input_1_handle = self._canonical_handle(cfg.get("input_1_handle") or "input1")
        input_2_handle = self._canonical_handle(cfg.get("input_2_handle") or "input2")
        input_1_field = str(cfg.get("input_1_field") or "").strip()
        input_2_field = str(cfg.get("input_2_field") or "").strip()
        allow_missing_branch_fallback = bool(
            cfg.get("allow_missing_branch_fallback", False)
        )
        input_count = self._normalize_input_count(cfg.get("input_count"))

        normalized_inputs = self._normalize_inputs(valid_inputs)
        grouped_payloads = self._group_payloads_by_handle(normalized_inputs)
        fallback_handles = list(grouped_payloads.keys())
        available_handles = sorted(grouped_payloads.keys())

        if mode in {"append"}:
            return {
                output_key: [item.get("data") for item in normalized_inputs]
            }

        if mode in {"choose_input_1", "choose_input_2", "choose_branch"}:
            if mode == "choose_input_1":
                selected_handle = input_1_handle
            elif mode == "choose_input_2":
                selected_handle = input_2_handle
            else:
                selected_handle = choose_branch

            self._validate_handle_within_input_count(
                selected_handle=selected_handle,
                input_count=input_count,
                config_key="choose_branch" if mode == "choose_branch" else (
                    "input_1_handle" if mode == "choose_input_1" else "input_2_handle"
                ),
            )
            selected = list(grouped_payloads.get(selected_handle, []))
            if not selected:
                if allow_missing_branch_fallback and fallback_handles:
                    # Explicit legacy mode: preserve old fallback behavior only when requested.
                    selected = list(grouped_payloads.get(fallback_handles[0], []))
                else:
                    if not selected_handle:
                        raise ValueError(
                            "MergeRunner: selected branch handle is empty. "
                            "Set choose_branch/input_1_handle/input_2_handle to a valid handle "
                            "or set allow_missing_branch_fallback=true for legacy fallback."
                        )
                    raise ValueError(
                        "MergeRunner: selected handle "
                        f"'{selected_handle}' was not found in incoming inputs. "
                        f"Available handles: {', '.join(available_handles) or '(none)'}. "
                        "Set allow_missing_branch_fallback=true to preserve legacy fallback behavior."
                    )
            if len(selected) == 0:
                return {output_key: []}
            if len(selected) == 1:
                return selected[0]
            return {output_key: selected}

        if mode == "combine":
            combined: dict[str, Any] = {}
            for idx, item in enumerate([normalized.get("data") for normalized in normalized_inputs]):
                if not isinstance(item, dict):
                    raise ValueError(
                        "MergeRunner: combine mode expects each branch output to be an object. "
                        f"Item at index {idx} is {type(item).__name__}. "
                        "Use append mode for non-object branch outputs."
                    )
                combined.update(item)
            return combined

        if mode == "combine_by_position":
            self._validate_handle_within_input_count(
                selected_handle=input_1_handle,
                input_count=input_count,
                config_key="input_1_handle",
            )
            self._validate_handle_within_input_count(
                selected_handle=input_2_handle,
                input_count=input_count,
                config_key="input_2_handle",
            )
            self._require_handles_present_for_mode(
                mode=mode,
                required_handles=[input_1_handle, input_2_handle],
                available_handles=available_handles,
            )
            input_1_payloads = list(grouped_payloads.get(input_1_handle, []))
            input_2_payloads = list(grouped_payloads.get(input_2_handle, []))
            items_1 = self._collect_items(input_1_payloads)
            items_2 = self._collect_items(input_2_payloads)
            combined_items = self._combine_by_position(
                items_1=items_1,
                items_2=items_2,
                join_type=join_type,
            )
            return {output_key: combined_items}

        if mode == "combine_by_fields":
            if not input_1_field or not input_2_field:
                raise ValueError(
                    "MergeRunner: combine_by_fields mode requires input_1_field and input_2_field."
                )
            self._validate_handle_within_input_count(
                selected_handle=input_1_handle,
                input_count=input_count,
                config_key="input_1_handle",
            )
            self._validate_handle_within_input_count(
                selected_handle=input_2_handle,
                input_count=input_count,
                config_key="input_2_handle",
            )
            self._require_handles_present_for_mode(
                mode=mode,
                required_handles=[input_1_handle, input_2_handle],
                available_handles=available_handles,
            )
            input_1_payloads = list(grouped_payloads.get(input_1_handle, []))
            input_2_payloads = list(grouped_payloads.get(input_2_handle, []))
            items_1 = self._collect_items(input_1_payloads)
            items_2 = self._collect_items(input_2_payloads)
            combined_items = self._combine_by_fields(
                items_1=items_1,
                items_2=items_2,
                input_1_field=input_1_field,
                input_2_field=input_2_field,
                join_type=join_type,
            )
            return {output_key: combined_items}

        raise ValueError(
            "MergeRunner: unsupported mode. "
            "Use one of: append, combine, combine_by_position, combine_by_fields, choose_branch, choose_input_1, choose_input_2."
        )

    @staticmethod
    def _unwrap_payload(item: Any) -> Any:
        if (
            isinstance(item, dict)
            and "data" in item
            and ("handle" in item or "source_node_id" in item)
        ):
            return item.get("data")
        return item

    def _normalize_inputs(self, items: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in items:
            payload = self._unwrap_payload(item)
            handle_raw = item.get("handle") if isinstance(item, dict) else None
            normalized.append(
                {
                    "handle": self._canonical_handle(handle_raw),
                    "data": payload,
                }
            )
        return normalized

    def _group_payloads_by_handle(
        self,
        items: list[dict[str, Any]],
    ) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        auto_index = 1

        for item in items:
            handle = item.get("handle")
            payload = item.get("data")

            if not handle:
                while f"input{auto_index}" in grouped:
                    auto_index += 1
                handle = f"input{auto_index}"
                auto_index += 1

            grouped.setdefault(handle, []).append(payload)

        return grouped

    @staticmethod
    def _normalize_input_count(raw_count: Any) -> int:
        try:
            parsed = int(raw_count)
        except Exception:
            return 2
        return min(6, max(2, parsed))

    @classmethod
    def _validate_handle_within_input_count(
        cls,
        *,
        selected_handle: str,
        input_count: int,
        config_key: str,
    ) -> None:
        if not selected_handle:
            return
        match = re.fullmatch(r"input(\d+)", selected_handle)
        if not match:
            return
        index = int(match.group(1))
        if index <= input_count:
            return
        raise ValueError(
            "MergeRunner: configured handle "
            f"'{selected_handle}' for {config_key} exceeds input_count={input_count}. "
            f"Use one of input1..input{input_count}, or increase input_count."
        )

    @staticmethod
    def _require_handles_present_for_mode(
        *,
        mode: str,
        required_handles: list[str],
        available_handles: list[str],
    ) -> None:
        missing = [
            handle for handle in required_handles if handle and handle not in available_handles
        ]
        if not missing:
            return
        missing_display = ", ".join(missing)
        available_display = ", ".join(available_handles) or "(none)"
        raise ValueError(
            f"MergeRunner: {mode} requires connected inputs for handle(s): {missing_display}. "
            f"Available handles: {available_display}. "
            "Connect the missing branch handles or update merge handle config/input_count."
        )

    @classmethod
    def _canonical_handle(cls, raw_handle: Any) -> str:
        handle = str(raw_handle or "").strip().lower()
        if not handle:
            return ""
        aliases = {
            "input_1": "input1",
            "left": "input1",
            "in1": "input1",
            "a": "input1",
            "1": "input1",
            "input_2": "input2",
            "right": "input2",
            "in2": "input2",
            "b": "input2",
            "2": "input2",
        }
        return aliases.get(handle, handle)

    @staticmethod
    def _normalize_mode(raw_mode: str) -> str:
        mode = str(raw_mode or "append").strip().lower()
        if mode in {"choose_input1", "choose_input_1", "passthrough", "pass_through", "pass-through", "pass"}:
            return "choose_input_1"
        if mode in {"choose_input2", "choose_input_2"}:
            return "choose_input_2"
        if mode in {"choose", "choose_branch", "choose_input"}:
            return "choose_branch"
        return mode

    @staticmethod
    def _collect_items(payloads: list[Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for payload in payloads:
            if isinstance(payload, list):
                source = payload
            else:
                source = [payload]
            for item in source:
                if isinstance(item, dict):
                    items.append(dict(item))
                else:
                    items.append({"_value": item})
        return items

    @staticmethod
    def _combine_by_position(
        *,
        items_1: list[dict[str, Any]],
        items_2: list[dict[str, Any]],
        join_type: str,
    ) -> list[dict[str, Any]]:
        left_len = len(items_1)
        right_len = len(items_2)

        if join_type == "inner":
            size = min(left_len, right_len)
        elif join_type == "left":
            size = left_len
        elif join_type == "right":
            size = right_len
        elif join_type == "outer":
            size = max(left_len, right_len)
        else:
            raise ValueError("MergeRunner: join_type must be one of inner, left, right, outer.")

        merged: list[dict[str, Any]] = []
        for idx in range(size):
            left = items_1[idx] if idx < left_len else None
            right = items_2[idx] if idx < right_len else None
            if left is None and right is None:
                continue
            if left is None:
                merged.append(dict(right or {}))
                continue
            if right is None:
                merged.append(dict(left))
                continue
            merged.append({**left, **right})
        return merged

    def _combine_by_fields(
        self,
        *,
        items_1: list[dict[str, Any]],
        items_2: list[dict[str, Any]],
        input_1_field: str,
        input_2_field: str,
        join_type: str,
    ) -> list[dict[str, Any]]:
        groups_1: dict[str, list[dict[str, Any]]] = {}
        groups_2: dict[str, list[dict[str, Any]]] = {}

        for item in items_1:
            key = self._field_key(item, input_1_field)
            groups_1.setdefault(key, []).append(item)
        for item in items_2:
            key = self._field_key(item, input_2_field)
            groups_2.setdefault(key, []).append(item)

        keys_1 = set(groups_1.keys())
        keys_2 = set(groups_2.keys())
        if join_type == "inner":
            keys = keys_1 & keys_2
        elif join_type == "left":
            keys = keys_1
        elif join_type == "right":
            keys = keys_2
        elif join_type == "outer":
            keys = keys_1 | keys_2
        else:
            raise ValueError("MergeRunner: join_type must be one of inner, left, right, outer.")

        merged: list[dict[str, Any]] = []
        for key in sorted(keys):
            left_rows = groups_1.get(key, [])
            right_rows = groups_2.get(key, [])

            if left_rows and right_rows:
                for left in left_rows:
                    for right in right_rows:
                        merged.append({**left, **right})
                continue

            if left_rows and join_type in {"left", "outer"}:
                merged.extend(dict(row) for row in left_rows)
                continue

            if right_rows and join_type in {"right", "outer"}:
                merged.extend(dict(row) for row in right_rows)

        return merged

    def _field_key(self, payload: dict[str, Any], path: str) -> str:
        value = self._resolve_field(payload, path)
        return f"{type(value).__name__}:{value}"

    @staticmethod
    def _resolve_field(payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in [segment for segment in str(path).split(".") if segment]:
            if isinstance(current, dict):
                current = current.get(part)
                continue
            if isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
                continue
            return None
        return current
