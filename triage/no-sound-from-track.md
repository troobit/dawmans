---
devices: [ableton/live-12]
---

# No sound from a track

also: the track is silent; I can't hear track 3; nothing comes out of one track

Work down the list in order. The first two account for most of it, and both are one click
away from something you meant to do.

## The Track Activator is off
check: the Track Activator switch at the bottom of the track is unlit
why: it sits next to the volume slider, so it is caught by a mis-aimed click more often
than anything else here
fix: ableton/live-12 §18.1 "The Live Mixer"

## Another track is soloed
check: a Solo switch is lit on some other track
fix: ableton/live-12 §18.6 "Soloing and Cueing"

## The track's Monitor is set to Off
check: the Monitor radio button in the In/Out section shows Off while the input meter moves
fix: ableton/live-12 §17.1 "Monitoring"

## The track's output is routed somewhere you are not listening
check: the track's Audio/MIDI To chooser names an output other than the one your speakers
are on
fix: ableton/live-12 §17 "Routing and I/O"

## A device in the chain is deactivated
check: a device's Activator toggle in its title bar is unlit, so the chain passes nothing on
fix: ableton/live-12 §23.2.1 "Device Title Bar"

## Otherwise
Check the Main track before assuming this track is at fault: its own Track Activator, its
volume and its output routing silence everything downstream of them.
