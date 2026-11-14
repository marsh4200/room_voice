"""Conversation agent for Room voice."""

from __future__ import annotations

import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN
from .parser import Match, parse

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    async_add_entities([RoomVoiceAgent(hass, entry)])


class RoomVoiceAgent(conversation.ConversationEntity):
    """Handles house commands from its own room list, passes the rest on."""

    _attr_has_entity_name = False
    _attr_name = "Room voice"
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._attr_unique_id = entry.entry_id

    @property
    def supported_languages(self):
        return MATCH_ALL

    def _reply(self, user_input, text: str, error: bool = False):
        response = intent.IntentResponse(language=user_input.language)
        if error:
            response.async_set_error(intent.IntentResponseErrorCode.NO_INTENT_MATCH, text)
        else:
            response.async_set_speech(text)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id
        )

    async def async_process(self, user_input: conversation.ConversationInput):
        data = self.hass.data[DOMAIN]["data"]
        try:
            match = parse(user_input.text, data.get("rooms", []))
        except Exception:  # never let a parsing bug kill the pipeline
            _LOGGER.exception("Room voice could not parse: %s", user_input.text)
            match = None

        if match is None:
            return await self._fallback(user_input, data.get("fallback") or "")
        if match.ask:
            return self._reply(user_input, match.ask)
        if not match.items:
            return self._reply(user_input, f"There's nothing like that set up in {match.room['name']}.")
        try:
            return self._reply(user_input, await self._run(match, user_input))
        except Exception:
            _LOGGER.exception("Room voice could not run: %s", user_input.text)
            return self._reply(user_input, "Something went wrong doing that.", error=True)

    async def _fallback(self, user_input, agent_id: str):
        if not agent_id or agent_id == self.entity_id:
            return self._reply(user_input, "I don't know that room or item.", error=True)
        return await conversation.async_converse(
            hass=self.hass,
            text=user_input.text,
            conversation_id=user_input.conversation_id,
            context=user_input.context,
            language=user_input.language,
            agent_id=agent_id,
            device_id=user_input.device_id,
        )

    async def _call(self, domain: str, service: str, entity_ids: list[str], context, **data) -> None:
        if entity_ids:
            await self.hass.services.async_call(
                domain, service, {"entity_id": entity_ids, **data}, blocking=True, context=context
            )

    async def _run(self, match: Match, user_input) -> str:
        ctx = user_input.context
        ids = [it["entity_id"] for it in match.items]

        def of(*domains):
            return [e for e in ids if e.split(".")[0] in domains]

        covers = of("cover")
        run_only = of("scene", "script")
        others = [e for e in ids if e not in covers and e not in run_only]

        if match.action in ("on", "off"):
            await self._call("homeassistant", f"turn_{match.action}", others, ctx)
            if match.action == "on":
                await self._call("homeassistant", "turn_on", run_only, ctx)
            if not others and not (match.action == "on" and run_only):
                if covers:
                    await self._call(
                        "cover", "open_cover" if match.action == "on" else "close_cover", covers, ctx
                    )
                else:
                    return f"I can't turn {match.action} {match.label}."
            return f"{match.label} {match.action}."

        if match.action in ("open", "close"):
            if not covers:
                return f"There's nothing to {match.action} in {match.label}."
            await self._call("cover", f"{match.action}_cover", covers, ctx)
            return f"{match.label} {'opened' if match.action == 'open' else 'closed'}."

        if match.action == "brightness":
            lights = of("light")
            if not lights:
                return f"{match.label} can't be dimmed."
            await self._call("light", "turn_on", lights, ctx, brightness_pct=match.value)
            return f"{match.label} set to {match.value} percent."

        if match.action == "temperature":
            climates = of("climate")
            if not climates:
                return f"There's no aircon set up in {match.label}."
            await self._call("climate", "set_temperature", climates, ctx, temperature=match.value)
            return f"{match.label} set to {match.value} degrees."

        return "I can't do that yet."
