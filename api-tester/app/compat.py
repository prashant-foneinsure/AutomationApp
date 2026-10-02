"""Pydantic v1/v2 compatibility.

The installed pydantic is 1.10.x (paired with fastapi 0.109), but the code is
written to work unchanged on v2 so upgrading later is not a rewrite. Only the
two places that actually differ are wrapped.
"""
import pydantic

PYDANTIC_V2 = pydantic.VERSION.startswith("2")


def to_dict(model, *, exclude_unset: bool = False, exclude_none: bool = False) -> dict:
    """model_dump() on v2, .dict() on v1."""
    if PYDANTIC_V2:
        return model.model_dump(exclude_unset=exclude_unset,
                                exclude_none=exclude_none)
    return model.dict(exclude_unset=exclude_unset, exclude_none=exclude_none)
