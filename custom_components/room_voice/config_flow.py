"""Config flow for Room voice."""

from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN


class RoomVoiceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One-click setup; everything else is done in the Room voice panel."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Room voice", data={})
        return self.async_show_form(step_id="user")
