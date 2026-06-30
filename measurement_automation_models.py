from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutomationStep:
    name: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    required: bool = False
    enabled: bool = True
    description: str = ""


@dataclass
class PrestartAutomationPlan:
    name: str
    steps: list[AutomationStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
