---
devices: [akai/apc-key-25@mk2, ableton/live-12]
---

# The controller does nothing

also: the pads do not light; the knobs move nothing; the keyboard is dead

## The Track, Sync and Remote switches are off for that MIDI port
check: the port is listed in the Settings with Track, Sync and Remote all off
fix: ableton/live-12 §17.3.1 "MIDI Port Inputs and Outputs"
fix: ableton/live-12 §17.3.1.1 "Track"
fix: ableton/live-12 §17.3.1.2 "Sync"
fix: ableton/live-12 §17.3.1.3 "Remote"

## No control surface is selected for it
check: the Control Surface chooser in the Link, Tempo & MIDI tab is empty, or names ports
the controller is not on
fix: ableton/live-12 §33.1.1 "Natively Supported Control Surfaces"
fix: ableton/live-12 §33.1.2 "Manual Control Surface Setup"

## The bank is parked over tracks you are not playing
check: the red rectangle in Session View sits away from the tracks you expect; hold Shift
and press the arrow Clip Stop Buttons to move it back
fix: akai/apc-key-25 "Features"

## Otherwise
A controller that lights up but changes nothing is mapped; a controller that does not light
up at all is a cable, a hub or a port, and nothing in the software will fix it.
