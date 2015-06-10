#!/bin/bash

SERVICE_NAME=adb-server
UPSTART_CONF_DIR=/etc/init

echo "Trying to create service \"$SERVICE_NAME\"..."
if [ -f ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf ]
then
    echo "There is a service with such name already. Change SERVICE_NAME in $0"
    exit 1
fi

echo 'description "adb-server daemon"
setuid v4android
setgid v4android
start on runlevel [2345]
stop on runlevel [06]

script
    /home/v4android/Android/Sdk/platform-tools/adb kill-server
    /home/v4android/Android/Sdk/platform-tools/adb -a fork-server server
end script

respawn
respawn limit 10 90' > ${UPSTART_CONF_DIR}/${SERVICE_NAME}.conf

[ $? == 0 ] || exit 1
echo "Service \"$SERVICE_NAME\" successfully created"
