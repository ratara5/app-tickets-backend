import importlib
import pkgutil
from typing import Callable, Any, Type
from inspect import iscoroutinefunction
from pydantic import BaseModel

type Entry = dict[str, Callable | Type[BaseModel]]
REGISTRY : dict[str, Entry] = {}

def service(schema: Type[BaseModel]):
    def decorator(fn: Callable) -> Callable: #Antes era def service cuando no se enviaba schema como parámetro
        REGISTRY[fn.__name__] = fn
        return fn
    return decorator

def _autodiscover(package: str) -> None:
    """Importa todos los módulos *_service del package para que se registren."""
    pkg = importlib.import_module(package)
    for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
        if module_name.ends_with("_service"):
            importlib.import_module(f"{package}.{module_name}")

async def dispatch_service(table: str, *args) -> Any: # y column: str?
    key = f"create_new_{table}"
    entry = REGISTRY.get(key)
    if entry is None:
        raise ValueError(f"Sin handler para {key!r}. Disponibles: {list(REGISTRY)}")
    fn = entry["fn"]
    return await fn(*args) if iscoroutinefunction(fn) else fn(*args)

async def dispatch_build_path(parent_table: str, *args) -> Any: # y column: str?
    key = f"build_object_path_{parent_table}"
    entry = REGISTRY.get(key)
    if entry is None:
        raise ValueError(f"Sin handler para {key!r}. Disponibles: {list(REGISTRY)}")
    fn = entry["fn"]
    return await fn(*args) if iscoroutinefunction(fn) else fn(*args)



