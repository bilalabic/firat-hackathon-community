from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, model_validator


class PartialUpdate(BaseModel):
    """PATCH body: only the fields present are changed; `null` clears a field.

    Subclasses list the columns that cannot be cleared in `not_null_fields`.
    """

    model_config = ConfigDict(extra="forbid")

    not_null_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def _not_null_fields_are_not_cleared(self) -> Self:
        cleared = [
            name
            for name in self.not_null_fields
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"cannot be null: {', '.join(cleared)}")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)
