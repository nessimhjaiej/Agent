from fusion.alpha import AlphaFusion
from fusion.base import BaseFusion
from fusion.rrf import RRFFusion


class FusionFactory:
    _registry: dict[str, type[BaseFusion]] = {
        "alpha": AlphaFusion,
        "rrf": RRFFusion,
    }

    @classmethod
    def create(cls, fusion_type: str) -> BaseFusion:
        key = fusion_type.strip().lower()
        fusion_cls = cls._registry.get(key)
        if not fusion_cls:
            supported = ", ".join(sorted(cls._registry))
            raise ValueError(f"Unknown fusion type '{fusion_type}'. Supported: {supported}")
        return fusion_cls()
