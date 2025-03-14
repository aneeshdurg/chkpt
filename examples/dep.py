from dataclasses import dataclass, field


@dataclass
class State:
    x: list[int] = field(default_factory=list)
