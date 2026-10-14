import logging
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ICON,
    ATTR_STATE,
    Platform,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .common.base_entity import IntegrationBaseEntity, async_setup_base_entry
from .common.consts import (
    DOMAIN,
    ALL_EDGE_OS_UNITS,
    ATTR_ATTRIBUTES,
    ATTR_UNIT_CONVERTOR,
    ATTR_UNIT_INFORMATION,
    ATTR_UNIT_RATE,
    UNIT_MAPPING,
)
from .common.entity_descriptions import IntegrationSensorEntityDescription
from .common.enums import DeviceTypes
from .managers.airos import AirosCoordinator
from .managers.coordinator import Coordinator
from .models.config_data import CONF_DEVICE_TYPE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    if entry.data.get(CONF_DEVICE_TYPE) == "airOS":
        coordinator: AirosCoordinator = hass.data[DOMAIN][entry.entry_id]
        async_add_entities(
            [
                AirosSensor(hass, entry, coordinator, description)
                for description in AIROS_SENSOR_DESCRIPTIONS
            ],
            True,
        )
        return

    await async_setup_base_entry(
        hass,
        entry,
        Platform.SENSOR,
        IntegrationSensorEntity,
        async_add_entities,
    )


class IntegrationSensorEntity(IntegrationBaseEntity, SensorEntity):
    """Representation of a sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        entity_description: IntegrationSensorEntityDescription,
        coordinator: Coordinator,
        device_type: DeviceTypes,
        item_id: str | None,
    ):
        super().__init__(hass, entity_description, coordinator, device_type, item_id)

        self._attr_device_class = entity_description.device_class
        self._attr_native_unit_of_measurement = (
            entity_description.native_unit_of_measurement
        )

        self._format_digits: int | None = None
        self._unit_convertor: Callable[[float], float] | None = None

        if self._attr_native_unit_of_measurement in ALL_EDGE_OS_UNITS:
            self._format_digits = 0

        if self._attr_device_class in [
            SensorDeviceClass.DATA_SIZE,
            SensorDeviceClass.DATA_RATE,
        ]:
            self._unit = coordinator.config_manager.unit

            unit_settings = UNIT_MAPPING.get(self._unit, {})
            unit_settings_information = unit_settings.get(
                ATTR_UNIT_INFORMATION, UnitOfInformation.BYTES
            )
            unit_settings_rate = unit_settings.get(
                ATTR_UNIT_RATE, UnitOfDataRate.BYTES_PER_SECOND
            )
            unit_convertor = unit_settings.get(ATTR_UNIT_CONVERTOR, lambda v: v)

            self._unit_convertor = unit_convertor
            self._format_digits = (
                0 if unit_settings_information == UnitOfInformation.BYTES else 3
            )

            if self._attr_device_class == SensorDeviceClass.DATA_SIZE:
                self._attr_native_unit_of_measurement = unit_settings_information

            if self._attr_device_class == SensorDeviceClass.DATA_RATE:
                self._attr_native_unit_of_measurement = unit_settings_rate

    def update_component(self, data):
        """Fetch new state parameters for the sensor."""
        if data is not None:
            state = data.get(ATTR_STATE)
            attributes = data.get(ATTR_ATTRIBUTES)
            icon = data.get(ATTR_ICON)

            if state is not None:
                if self._unit_convertor is not None:
                    state = self._unit_convertor(state)

                if self._format_digits is not None:
                    state = self._format_number(state, self._format_digits)

            self._attr_native_value = state
            self._attr_extra_state_attributes = attributes

            if icon is not None:
                self._attr_icon = icon

        else:
            self._attr_native_value = None

    @staticmethod
    def _format_number(value: int | float | None, digits: int = 0) -> int | float:
        if value is None:
            value = 0

        value_str = f"{value:.{digits}f}"
        result = int(value_str) if digits == 0 else float(value_str)

        return result



AIROS_SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="signal",
        name="Wireless signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="noise_floor",
        name="Wireless noise floor",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-distance-variant",
    ),
    SensorEntityDescription(
        key="ccq",
        name="Wireless CCQ",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
    ),
    SensorEntityDescription(
        key="frequency",
        name="Wireless frequency",
        native_unit_of_measurement="MHz",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
    ),
    SensorEntityDescription(
        key="channel",
        name="Wireless channel",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radio-tower",
    ),
    SensorEntityDescription(
        key="tx_link_rate",
        name="Wireless transmit link rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:upload-network-outline",
    ),
    SensorEntityDescription(
        key="rx_link_rate",
        name="Wireless receive link rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:download-network-outline",
    ),
    SensorEntityDescription(
        key="lan_received_bytes",
        name="LAN received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:download-network-outline",
    ),
    SensorEntityDescription(
        key="lan_sent_bytes",
        name="LAN sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:upload-network-outline",
    ),
    SensorEntityDescription(
        key="wlan_received_bytes",
        name="WLAN received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:download-network-outline",
    ),
    SensorEntityDescription(
        key="wlan_sent_bytes",
        name="WLAN sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:upload-network-outline",
    ),
    SensorEntityDescription(
        key="lan_received_rate",
        name="LAN receive rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:download-network-outline",
    ),
    SensorEntityDescription(
        key="lan_sent_rate",
        name="LAN send rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:upload-network-outline",
    ),
    SensorEntityDescription(
        key="wlan_received_rate",
        name="WLAN receive rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:download-network-outline",
    ),
    SensorEntityDescription(
        key="wlan_sent_rate",
        name="WLAN send rate",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:upload-network-outline",
    ),
)


class AirosSensor(CoordinatorEntity[AirosCoordinator], SensorEntity):
    """Sensor backed by a legacy airOS status field."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: AirosCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Ubiquiti",
            model="NanoStation / legacy airOS",
            name=entry.title,
        )

    @property
    def native_value(self):
        """Return the latest value for this sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)
