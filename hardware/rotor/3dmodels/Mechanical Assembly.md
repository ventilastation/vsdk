# Mechanical Assembly

There are a few mechanical pieces needed to build Ventilastation:

- Industrial fan, 30 inch
- Slip Ring
- Axle adapter (custom)
- Fan blade and slip ring support (custom)
- Magnet plus optional support
- 5 x 20mm M4 bolts
- 2 x tappered head screws

All custom parts were designed with OnShape, and a model of all the parts plus its full assembly can be [browsed online](https://cad.onshape.com/documents/144b7488125d50c53e25b44a/w/fe42cb03011735274a08db6c/e/ad9868ebba5a1ec7c2a41ef0?renderMode=0&uiState=67effda339f27b01d99b0478).

## Industrial fan, 30 inch

This is an off-the-shelf 30 inch industrial fan.
The ones where the base is shaped like a cross tend to work better.
A few pictures are included of one purchased in a generic homecenter in Argentina, that was originally made in Maylasia.
This has served for almost ten years as the only fan used for this project.

## Slip Ring

A slip ring has a part affixed to the motor of the fan (the stator), and a part affixed to the spinning blade (the rotor). Cables entering the slip ring thru the stator have a corresponding cable exiting thru the rotor, and the slip ring maintains connection between them as it is being spin. Just to be clear: a slip ring does not spin by itself, that's the responsability of the fan's motor.

The slip ring conducts the 5v power from the external power supply towards the blade assembly. It also allows the data signals to go back and forth, from the CPU in the blade to the external console.
The fan will spin at aprox 600 RPM, so a high speed Slip Ring is needed. We are currently using one with 6 cabled lanes, and a maximum rotation speed of 1500 RPM.

## Axle adapter (custom)

The axle adapter allows the slip ring and fan blade to be securely attached to the fan's axle.
This piece was lathe-machined out of a block of steel, but aluminum should work too.
In this folder you can find a PDF with a blueprint for this part, but it may have to be adjusted if your fan and/or slipring have different dimensions.

## Fan blade and slip ring support (custom)

The fan blade and slip ring support were laser-cut out of 2mm steel.
An included PDF provides a detailed blueprint for both parts.
The slip ring support blueprint may need to be changed if your fan and/or slipring have different dimensions.

## Magnet plus optional support

We are currently using a spherical magnet so the hall-effect sensor in the blade can understand when a new rotation begins. In previous versions a square magnet with a bit of bent metal as a support were used. Feel free to choose whatever way suits you best, but make sure the magnet is located in the bottommost part, on the inside of the fan cage, near but not touching the hall sensor in the blade.

## Bolts and screws

A few bolts and screws are used in the build:

4 x 20mm M4 bolts - these secure the fan blade to the axle adapter
1 x 20mm M4 bolt - this one secures the axle adapter to the fan axle
2 x 25mm M5 tapered head screws - these two prevent the slip ring stator from spinning