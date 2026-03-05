mkdir -p ~/.config/autostart
cat > ~/.config/autostart/vsbase.desktop <<EOF
[Desktop Entry]
Type=Application
Exec=~/vsdk/hardware/base/base-remote.sh
Hidden=false
NoDisplay=False
X-GNOME-Autostart-enabled=true
Name=Ventilastation Base
Comments=Starts the Ventilastation Base
EOF