#!/bin/sh
# Hora del sistema con el RTC DS3231, antes de arrancar el suscriptor.
#   - Con internet (NTP ya sincronizó): guarda esa hora en el RTC, que así se
#     mantiene corregido cada vez que la Pi arranca con red.
#   - Sin internet: carga en el sistema la hora del RTC.
# Lo ejecuta parkfinder.service como root (ExecStartPre). Si falla, el
# suscriptor igual verifica la hora y no registra con una hora falsa.

if [ ! -e /dev/rtc0 ]; then
    echo "hora_rtc: no hay RTC (/dev/rtc0), se depende de NTP"
    exit 0
fi

if [ "$(timedatectl show -p NTPSynchronized --value)" = "yes" ]; then
    hwclock --systohc --utc && echo "hora_rtc: RTC actualizado desde NTP ($(date))"
else
    hwclock --hctosys --utc && echo "hora_rtc: hora cargada desde el RTC ($(date))"
fi
