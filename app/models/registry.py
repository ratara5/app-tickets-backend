import importlib
import pkgutil

from sqlalchemy.orm import DeclarativeMeta

MODEL_REGISTRY: dict[str, type[DeclarativeMeta]] = {}

def register_model(model):
    table_name = getattr(model, "__tablename__", None)
    if not table_name:
        return model
    MODEL_REGISTRY[table_name] = model

    return model

def _autodiscover_models(package: str):
    pkg = importlib.import_module(package)

    for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
        if module_name.startswith("_"):
            continue
        importlib.import_module(
            f"{package}.{module_name}"
        )

def get_model(table_name: str):
    model = MODEL_REGISTRY.get(table_name)
    if model is None:
        raise ValueError(
            f"Model is not in registry: {table_name}"
        )

    return model