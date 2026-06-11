import re
from dataclasses import dataclass

SENSORY_PATTERN = re.compile(r'\(\*(.+?) 촉감놀이\)')
BASE_SUPPLIES = "편안한 복장, 물티슈, 마실물"
SENSORY_EXTRA = "여벌의 옷(미술가운)"


@dataclass
class SensoryResult:
    is_sensory: bool
    material: str
    supplies: str


def detect(content: str, base_supplies: str = BASE_SUPPLIES) -> SensoryResult:
    """활동 내용에서 촉감놀이 재료를 감지하고 준비물을 완성한다."""
    match = SENSORY_PATTERN.search(content)
    if not match:
        return SensoryResult(is_sensory=False, material="", supplies=base_supplies)

    material = match.group(1).strip()
    supplies = f"{base_supplies}, {SENSORY_EXTRA}"
    return SensoryResult(is_sensory=True, material=material, supplies=supplies)
