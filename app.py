"""Gene Day: daily answers from a plain DNA trait the user states (v0.1.1).

Privacy design, enforced by the shape of this app:

* The raw DNA file never reaches this app. It is read offline, on the
  user's own computer, with `local_reader/dna-reader.html`.
* This app only accepts plain trait words ("slow", "intolerant"). Anything
  that looks like a genotype or an rs number is refused, not used.
* Health risk results (the red tier) have no input here at all.
* Pippa runs every app with `persistence: none`, and the app is told nothing
  about who is asking, so it cannot keep or link anything.
"""

from __future__ import annotations

import re
from pathlib import Path

from pippa_agentapp_sdk import (
    AgentAppError,
    Call,
    Manifest,
    Result,
    load_manifest_file,
    validate_manifest,
)

MANIFEST_PATH = Path(__file__).with_name("manifest.yaml")

# Hours before bed to stop caffeine. A rough rule of thumb from caffeine's
# half life (about 5 hours on average, longer for slow CYP1A2 metabolisers).
CUTOFF_HOURS = {"fast": 6, "normal": 8, "slow": 10}
DEFAULT_BEDTIME = "23:00"

# Approximate grams of lactose per typical serving.
LACTOSE = {
    "milkshake": (20.0, "a 350 ml milkshake"),
    "hot chocolate": (13.0, "a mug made with milk"),
    "milk": (12.0, "a 250 ml glass"),
    "latte": (14.0, "a large latte"),
    "cappuccino": (7.0, "a regular cappuccino"),
    "flat white": (6.0, "a flat white"),
    "mac and cheese": (6.0, "a bowl"),
    "custard": (7.0, "a 150 g bowl"),
    "ice cream": (6.0, "two scoops, about 100 g"),
    "greek yogurt": (4.0, "a 150 g pot"),
    "yogurt": (6.0, "a 150 g pot"),
    "yoghurt": (6.0, "a 150 g pot"),
    "kefir": (3.0, "a 250 ml glass"),
    "cheesecake": (4.0, "a slice"),
    "cottage cheese": (3.0, "100 g"),
    "milk chocolate": (3.0, "a 40 g bar"),
    "cream": (1.0, "a 30 ml splash"),
    "pizza": (1.0, "a few slices"),
    "mozzarella": (0.3, "30 g"),
    "brie": (0.1, "30 g"),
    "butter": (0.1, "10 g on bread"),
    "cheddar": (0.1, "30 g"),
    "parmesan": (0.0, "a grated topping"),
    "cheese": (0.1, "30 g of hard cheese"),
    "oat milk": (0.0, "a 250 ml glass"),
    "soy milk": (0.0, "a 250 ml glass"),
    "almond milk": (0.0, "a 250 ml glass"),
    "lactose free milk": (0.0, "a 250 ml glass"),
}
# Longest names first, so "oat milk" wins over "milk".
FOODS = sorted(LACTOSE, key=len, reverse=True)

# Many lactose intolerant adults cope with about 12 g in one sitting.
USUALLY_OK_GRAMS = 12.0
FINE_GRAMS = 2.0

GENOTYPE = re.compile(r"\b[rR][sS]\d+|\b[ACGT]{2}\b|\b[ACGT]/[ACGT]\b")


class RawDnaRefused(AgentAppError):
    user_message = (
        "I only work with plain trait words like slow, fast, tolerant or "
        "intolerant. Please never send DNA letters or rs numbers to an app."
    )
    retryable = False


class MetabolismUnknown(AgentAppError):
    user_message = (
        "Tell me if you are a slow, normal or fast caffeine metaboliser, for "
        "example: I am a slow caffeine metaboliser, when is my last coffee?"
    )
    retryable = False


class BedtimeUnreadable(AgentAppError):
    user_message = "I could not read your bedtime. Try a time like 23:00."
    retryable = False


class FoodMissing(AgentAppError):
    user_message = "Tell me which food or drink, for example: how much lactose is in a latte?"
    retryable = False


class FoodUnknown(AgentAppError):
    user_message = "I do not have a lactose figure for that food yet."
    retryable = False


def _refuse_raw_dna(*values: str) -> None:
    for value in values:
        if value and GENOTYPE.search(value):
            raise RawDnaRefused("input looked like a genotype or rs number")


class App:
    def __init__(self) -> None:
        self._manifest = validate_manifest(load_manifest_file(MANIFEST_PATH))

    @property
    def manifest(self) -> Manifest:
        return self._manifest

    def handle(self, call: Call) -> Result:
        if call.outcome_id == "caffeine.cutoff":
            return self._caffeine(call)
        if call.outcome_id == "lactose.check":
            return self._lactose(call)
        raise AgentAppError(f"this app cannot do {call.outcome_id!r}")

    # caffeine
    def _caffeine(self, call: Call) -> Result:
        speed_text = (call.inputs.get("caffeine_metabolism") or "").strip()
        bed_text = (call.inputs.get("bedtime") or "").strip()
        _refuse_raw_dna(speed_text)

        speed = self._speed(speed_text)
        bed_minutes = self._clock(bed_text or DEFAULT_BEDTIME)
        hours = CUTOFF_HOURS[speed]
        cutoff = (bed_minutes - hours * 60) % (24 * 60)

        bed = self._fmt(bed_minutes)
        last = self._fmt(cutoff)
        sentence = (
            f"As a {speed} caffeine metaboliser going to bed at {bed}, "
            f"have your last coffee at {last}, {hours} hours before sleep."
        )
        if not bed_text:
            sentence += " I assumed a bedtime of 23:00."
        return Result(
            data={
                "last_coffee_time": last,
                "hours_before_bed": hours,
                "metabolism_used": speed,
                "bedtime_used": bed,
            },
            narrative=sentence,
        )

    @staticmethod
    def _speed(text: str) -> str:
        t = text.lower()
        if "slow" in t:
            return "slow"
        if "fast" in t or "rapid" in t:
            return "fast"
        if "normal" in t or "average" in t or "medium" in t:
            return "normal"
        raise MetabolismUnknown(f"no metabolism speed in {text!r}")

    @staticmethod
    def _clock(text: str) -> int:
        t = text.lower().replace(".", ":").replace(" ", "")
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)?", t)
        if not match:
            raise BedtimeUnreadable(f"could not read {text!r}")
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        suffix = match.group(3)
        if suffix == "pm" and hour < 12:
            hour += 12
        if suffix == "am" and hour == 12:
            hour = 0
        if hour > 23 or minute > 59:
            raise BedtimeUnreadable(f"out of range {text!r}")
        return hour * 60 + minute

    @staticmethod
    def _fmt(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    # lactose
    def _lactose(self, call: Call) -> Result:
        food_text = (call.inputs.get("food") or "").strip()
        status_raw = (call.inputs.get("lactose_status") or "").strip()
        _refuse_raw_dna(status_raw)
        status_text = status_raw.lower()
        if not food_text:
            raise FoodMissing("no food in the message")

        food = self._match_food(food_text)
        grams, serving = LACTOSE[food]
        tolerant = "intolerant" not in status_text and "tolerant" in status_text

        if tolerant or grams <= FINE_GRAMS:
            verdict, ok = "fine", True
        elif grams <= USUALLY_OK_GRAMS:
            verdict, ok = "usually ok", True
        else:
            verdict, ok = "likely symptoms", False

        sentence = f"{food[0].upper()}{food[1:]} ({serving}) has about {grams:g} g of lactose."
        if tolerant:
            sentence += " You digest lactose well, so that is no problem."
        elif verdict == "fine":
            sentence += " That is so little that it is fine even if you are lactose intolerant."
        elif verdict == "usually ok":
            sentence += (
                " Most lactose intolerant people cope with up to about 12 g in one"
                " sitting, so one serving is usually ok."
            )
        else:
            sentence += (
                " That is above the roughly 12 g most lactose intolerant people"
                " cope with, so pick a lactose free version or take lactase."
            )
        return Result(
            data={
                "food_matched": food,
                "serving": serving,
                "lactose_grams": round(grams, 1),
                "verdict": verdict,
                "likely_ok": ok,
            },
            narrative=sentence,
        )

    @staticmethod
    def _match_food(text: str) -> str:
        t = text.lower().replace("-", " ")
        for food in FOODS:
            if food in t:
                return food
        error = FoodUnknown(f"no lactose entry for {text!r}")
        error.user_message = f"I do not have a lactose figure for {text} yet."
        raise error
