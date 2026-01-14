"""Config flow for Deerma Water Purifier integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .api_client import DeermaAPIClient

_LOGGER = logging.getLogger(__name__)

STEP_LOGIN_TYPE_SCHEMA = vol.Schema(
    {
        vol.Required("login_type", default="password"): vol.In(["password", "captcha"]),
    }
)

STEP_PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required("phone"): str,
        vol.Required("password"): str,
    }
)

STEP_CAPTCHA_SCHEMA = vol.Schema(
    {
        vol.Required("phone"): str,
        vol.Required("captcha"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    login_type = data.get("login_type", "password")
    
    if login_type == "captcha":
        api_client = DeermaAPIClient(
            data["phone"],
            captcha=data.get("captcha"),
            login_type="captcha"
        )
    else:
        api_client = DeermaAPIClient(
            data["phone"],
            password=data.get("password"),
            login_type="password"
        )
    
    try:
        # Run login in executor to avoid blocking
        session_data = await hass.async_add_executor_job(api_client.login_sync)
        if not session_data or not session_data.get("access_token"):
            raise InvalidAuth
        
        # Get device list to verify connection
        devices = await hass.async_add_executor_job(api_client.get_devices_sync)
        _LOGGER.debug("Devices retrieved: %d devices", len(devices) if devices else 0)
        if not devices or len(devices) == 0:
            _LOGGER.warning("No devices found for account %s", data["phone"])
            # Don't raise error if login succeeded but no devices - allow user to proceed
        
        # Get first device ID - based on actual API response structure
        device_id = None
        if devices and len(devices) > 0:
            device_info = devices[0].get("device", {})
            device_id = device_info.get("id") or devices[0].get("device_id") or devices[0].get("id")
        
        return {
            "title": f"飞利浦水健康 ({data['phone']})",
            "access_token": session_data.get("access_token"),
            "refresh_token": session_data.get("refresh_token"),
            "user_id": session_data.get("user_id"),
            "device_id": device_id,
            "devices": devices,
        }
    except Exception as err:
        _LOGGER.exception("Unexpected exception during login")
        if isinstance(err, (InvalidAuth, CannotConnect)):
            raise
        raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deerma Water Purifier."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self.login_type = None
        self.phone = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - select login type."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_LOGIN_TYPE_SCHEMA
            )

        self.login_type = user_input["login_type"]
        
        if self.login_type == "password":
            return await self.async_step_password()
        else:
            return await self.async_step_captcha()

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle password login step."""
        errors = {}
        
        if user_input is None:
            return self.async_show_form(
                step_id="password", data_schema=STEP_PASSWORD_SCHEMA
            )

        self.phone = user_input["phone"]
        user_input["login_type"] = "password"

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(user_input["phone"])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=info["title"],
                data={
                    "phone": user_input["phone"],
                    "password": user_input["password"],
                    "login_type": "password",
                    "access_token": info.get("access_token"),
                    "refresh_token": info.get("refresh_token"),
                    "user_id": info.get("user_id"),
                    "device_id": info.get("device_id"),
                    "devices": info.get("devices", []),
                },
            )

        return self.async_show_form(
            step_id="password", data_schema=STEP_PASSWORD_SCHEMA, errors=errors
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle captcha login step."""
        errors = {}
        
        if user_input is None:
            # First time - request captcha
            if self.phone is None:
                # Need phone number first
                return self.async_show_form(
                    step_id="captcha_phone",
                    data_schema=vol.Schema({vol.Required("phone"): str}),
                )
            
            # Request captcha
            try:
                api_client = DeermaAPIClient(self.phone, login_type="captcha")
                await api_client.request_captcha()
                return self.async_show_form(
                    step_id="captcha",
                    data_schema=STEP_CAPTCHA_SCHEMA,
                    description_placeholders={"phone": self.phone},
                )
            except Exception as err:
                _LOGGER.exception("Failed to request captcha")
                errors["base"] = "captcha_request_failed"
                return self.async_show_form(
                    step_id="captcha_phone",
                    data_schema=vol.Schema({vol.Required("phone"): str}),
                    errors=errors,
                )
        
        # User entered captcha
        if "phone" in user_input and self.phone is None:
            # First step - save phone and request captcha
            self.phone = user_input["phone"]
            try:
                api_client = DeermaAPIClient(self.phone, login_type="captcha")
                await api_client.request_captcha()
                return self.async_show_form(
                    step_id="captcha",
                    data_schema=STEP_CAPTCHA_SCHEMA,
                    description_placeholders={"phone": self.phone},
                )
            except Exception as err:
                _LOGGER.exception("Failed to request captcha")
                errors["base"] = "captcha_request_failed"
                return self.async_show_form(
                    step_id="captcha_phone",
                    data_schema=vol.Schema({vol.Required("phone"): str}),
                    errors=errors,
                )
        
        # Second step - verify captcha and login
        user_input["login_type"] = "captcha"
        if self.phone:
            user_input["phone"] = self.phone

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(user_input["phone"])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=info["title"],
                data={
                    "phone": user_input["phone"],
                    "login_type": "captcha",
                    "access_token": info.get("access_token"),
                    "refresh_token": info.get("refresh_token"),
                    "user_id": info.get("user_id"),
                    "device_id": info.get("device_id"),
                    "devices": info.get("devices", []),
                },
            )

        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_SCHEMA,
            description_placeholders={"phone": self.phone},
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
