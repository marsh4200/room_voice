"""Room voice: a voice agent that uses its own room and item names."""

from __future__ import annotations

import os

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import DOMAIN, PANEL_URL, STATIC_URL, STORAGE_KEY, STORAGE_VERSION

PLATFORMS = [Platform.CONVERSATION]

ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Optional("aliases", default=list): [cv.string],
    }
)
ROOM_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("aliases", default=list): [cv.string],
        vol.Optional("items", default=list): [ITEM_SCHEMA],
    }
)
CONFIG_SCHEMA_WS = vol.Schema(
    {
        vol.Optional("fallback", default=""): cv.string,
        vol.Optional("reply", default="Okay"): cv.string,
        vol.Optional("rooms", default=list): [ROOM_SCHEMA],
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    data = await store.async_load() or {"fallback": "", "rooms": []}
    shared = hass.data.setdefault(DOMAIN, {})
    shared["store"] = store
    shared["data"] = data

    if not shared.get("ws_registered"):
        websocket_api.async_register_command(hass, ws_get)
        websocket_api.async_register_command(hass, ws_save)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, os.path.join(os.path.dirname(__file__), "frontend"), False)]
        )
        shared["ws_registered"] = True

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="room-voice-panel",
        frontend_url_path=PANEL_URL,
        module_url=f"{STATIC_URL}/panel.js",
        sidebar_title="Room voice",
        sidebar_icon="mdi:microphone-message",
        require_admin=True,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    frontend.async_remove_panel(hass, PANEL_URL)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@websocket_api.websocket_command({vol.Required("type"): "room_voice/get"})
@websocket_api.require_admin
@callback
def ws_get(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], hass.data[DOMAIN]["data"])


@websocket_api.websocket_command(
    {vol.Required("type"): "room_voice/save", vol.Required("config"): CONFIG_SCHEMA_WS}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass: HomeAssistant, connection, msg) -> None:
    shared = hass.data[DOMAIN]
    shared["data"] = msg["config"]
    await shared["store"].async_save(msg["config"])
    connection.send_result(msg["id"], {"ok": True})
