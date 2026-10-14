"""
This component provides support for EdgeOS based devices.
For more details about this component, please refer to the documentation at
https://github.com/elad-bar/ha-EdgeOS
"""
import logging
import sys

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_START,
    Platform,
)
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.core import HomeAssistant

from .common.consts import DEFAULT_NAME, DOMAIN
from .common.entity_descriptions import PLATFORMS
from .managers.airos import AirosCoordinator
from .managers.config_manager import ConfigManager
from .managers.coordinator import Coordinator
from .managers.password_manager import PasswordManager
from .models.config_data import CONF_DEVICE_TYPE
from .models.exceptions import LoginError

_LOGGER = logging.getLogger(__name__)


async def async_setup(_hass, _config):
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a EdgeOS component."""
    initialized = False

    try:
        _LOGGER.debug("Setting up")
        entry_config = {key: entry.data[key] for key in entry.data}

        _LOGGER.debug("Starting up password manager")
        await PasswordManager.decrypt(hass, entry_config, entry.entry_id)

        if entry_config.get(CONF_DEVICE_TYPE) == "airOS":
            coordinator = AirosCoordinator(
                hass,
                entry_config[CONF_HOST],
                entry_config[CONF_USERNAME],
                entry_config[CONF_PASSWORD],
                entry.entry_id,
            )
            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
            try:
                await coordinator.async_config_entry_first_refresh()
            except Exception as ex:
                raise ConfigEntryNotReady(
                    "Unable to connect to the airOS device"
                ) from ex
            await hass.config_entries.async_forward_entry_setups(
                entry, [Platform.SENSOR]
            )
            return True

        _LOGGER.debug("Starting up configuration manager")
        config_manager = ConfigManager(hass, entry)
        await config_manager.initialize(entry_config)

        is_initialized = config_manager.is_initialized

        if is_initialized:
            _LOGGER.debug("Starting up coordinator")
            coordinator = Coordinator(hass, config_manager)

            hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

            if hass.is_running:
                _LOGGER.debug("Initializing coordinator")
                await coordinator.initialize()

            else:
                _LOGGER.debug("Registering listener for HA started event")
                hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_START, coordinator.on_home_assistant_start
                )

            _LOGGER.info("Finished loading integration")

        initialized = is_initialized

        _LOGGER.debug(f"Setup status: {is_initialized}")

    except ConfigEntryNotReady:
        raise

    except LoginError:
        _LOGGER.info(f"Failed to login {DEFAULT_NAME} API, cannot log integration")

    except Exception as ex:
        exc_type, exc_obj, tb = sys.exc_info()
        line_number = tb.tb_lineno

        _LOGGER.error(
            f"Failed to load {DEFAULT_NAME}, error: {ex}, line: {line_number}"
        )

    return initialized


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info(f"Unloading {DOMAIN} integration, Entry ID: {entry.entry_id}")

    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.terminate()

    if entry.data.get(CONF_DEVICE_TYPE) == "airOS":
        unloaded = await hass.config_entries.async_unload_platforms(
            entry, [Platform.SENSOR]
        )
        if unloaded:
            del hass.data[DOMAIN][entry.entry_id]
        return unloaded

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, platform)

    del hass.data[DOMAIN][entry.entry_id]

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info(f"Removing {DOMAIN} integration, Entry ID: {entry.entry_id}")

    entry_id = entry.entry_id

    if entry.data.get(CONF_DEVICE_TYPE) == "airOS":
        return await async_unload_entry(hass, entry)

    coordinator: Coordinator = hass.data[DOMAIN][entry_id]
    await coordinator.config_manager.remove(entry_id)
    return await async_unload_entry(hass, entry)
