#!/usr/bin/env python3
import dbus

BLUEZ_SERVICE = "org.bluez"
BLUEZ_DEVICE_IFACE = BLUEZ_SERVICE + ".Device1"


def get_device_property(device, property):
    properties = dbus.Interface(device, dbus.PROPERTIES_IFACE)
    return properties.Get(BLUEZ_DEVICE_IFACE, property)


def main():
    bus = dbus.SystemBus()
    manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE, "/"),
        "org.freedesktop.DBus.ObjectManager"
    )
    devices = [
        dbus.Interface(
            bus.get_object(BLUEZ_SERVICE, obj_path), BLUEZ_DEVICE_IFACE
        )
        for obj_path, obj_ifaces in manager.GetManagedObjects().items()
        if BLUEZ_DEVICE_IFACE in obj_ifaces
    ]

    if not devices:
        return

    devices.sort(key=lambda dev: get_device_property(dev, "Name"))

    connected_device = None
    for idx, device in enumerate(devices):
        if get_device_property(device, "Connected"):
            connected_device = device
            devices = devices[(idx + 1):] + devices[:idx]
            break

    if devices:
        if connected_device is not None:
            connected_device.Disconnect()

        for device in devices:
            try:
                device.Connect()
                break
            except dbus.exceptions.DBusException:
                pass


if __name__ == "__main__":
    main()
