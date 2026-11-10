"""YAML 严格读取与内容摘要。

摘要规则 (故事与映射共用):
1. 先把 YAML 解析为数据, 再做确定性序列化, 不对原文本取哈希, 注释/缩进/引号风格/键顺序变化不影响摘要。
2. 顶层 `digest` 字段不参与计算 (避免自引用); 若文件写了 `digest` 则必须与计算值一致。
3. 映射 (dict) 按键排序; 列表保持原顺序, 顺序变化视为内容变化
   (main_flow 的步骤顺序有业务含义, 其余列表按保守原则同样处理)。
4. 字符串做 Unicode NFC 规范化; 不做其他裁剪。
5. 序列化为 JSON(sort_keys, 紧凑分隔符, ensure_ascii=False), 取 UTF-8 的 SHA-256, 结果形如 `sha256:<hex>`。

读取约束: 重复键直接报错 (PyYAML 默认静默覆盖); 时间戳不隐式转换为 datetime, 保持字符串。
"""
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

DIGEST_FIELD = "digest"


class YamlLoadError(Exception):
    pass


class _StrictLoader(yaml.SafeLoader):
    pass


# 不把 2026-01-01 之类隐式转成 date/datetime, 否则摘要与时间语义都依赖解析器
_StrictLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False):
    seen = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=True)
        try:
            hash(key)
        except TypeError:
            raise ConstructorError(None, None, f"unhashable mapping key: {key!r}", key_node.start_mark)
        if key in seen:
            raise ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_yaml_text(text: str) -> Any:
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as e:
        raise YamlLoadError(str(e).replace("\n", " ")) from e


def load_yaml_file(path: Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise YamlLoadError(f"cannot read {path}: {e}") from e
    return load_yaml_text(text)


def _normalize(obj: Any, where: str = "$") -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise YamlLoadError(f"non-string key {k!r} at {where}")
            nk = unicodedata.normalize("NFC", k)
            if nk in out:
                raise YamlLoadError(f"keys collide after NFC normalization at {where}: {k!r}")
            out[nk] = _normalize(v, f"{where}.{k}")
        return out
    if isinstance(obj, list):
        return [_normalize(v, f"{where}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            raise YamlLoadError(f"non-finite float at {where}")
        return obj
    raise YamlLoadError(f"unsupported value type {type(obj).__name__} at {where}")


def canonical_bytes(data: Any) -> bytes:
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != DIGEST_FIELD}
    norm = _normalize(data)
    return json.dumps(
        norm, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def content_digest(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(data)).hexdigest()
