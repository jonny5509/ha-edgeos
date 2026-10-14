from homeassistant.components.update import UpdateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .common.base_entity import IntegrationBaseEntity, async_setup_base_entry
from .common.entity_descriptions import IntegrationUpdateEntityDescription
from .common.enums import DeviceTypes
from .managers.coordinator import Coordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    await async_setup_base_entry(
        hass,
        entry,
        Platform.UPDATE,
        IntegrationUpdateEntity,
        async_add_entities,
    )


class IntegrationUpdateEntity(IntegrationBaseEntity, UpdateEntity):
    """Representation of an EdgeOS firmware update."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_description: IntegrationUpdateEntityDescription,
        coordinator: Coordinator,
        device_type: DeviceTypes,
        item_id: str | None,
    ):
        super().__init__(hass, entity_description, coordinator, device_type, item_id)
        self._attr_title = "EdgeOS firmware"

    def update_component(self, data):
        """Update firmware version information from the coordinator."""
        if data is None:
            self._attr_installed_version = None
            self._attr_latest_version = None
            self._attr_release_url = None
            return

        self._attr_installed_version = data.get("installed_version")
        self._attr_latest_version = data.get("latest_version")
        self._attr_release_url = data.get("release_url")
        self._attr_title = data.get("title", "EdgeOS firmware")
