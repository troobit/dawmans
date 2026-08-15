---
devices: [ableton/live-12]
---

# A track is distorting

also: the kick is crunchy; a track sounds crushed; the mix is clipping

## The distortion is deliberate
check: the chain holds Saturator, Drum Buss, Overdrive, Vinyl Distortion, Dynamic Tube or Amp
why: these are documented at length and the word "distortion" belongs to them, so a search
answers with the device you added on purpose unless it is eliminated first
fix: ableton/live-12 §28.34 "Saturator"
fix: ableton/live-12 §28.12 "Drum Buss"
fix: ableton/live-12 §28.27 "Overdrive"
fix: ableton/live-12 §28.41 "Vinyl Distortion"
fix: ableton/live-12 §28.13 "Dynamic Tube"
fix: ableton/live-12 §28.1 "Amp"

## The input is clipping before Live records it
check: the Input Channel meter in the In/Out section flashes red while you play
fix: ableton/live-12 §17.2 "External Audio In/Out"

## A device is putting out more than 0 dB
check: the track meter peaks past 0 dB with the device on and does not with it off
fix: ableton/live-12 §18.1.1 "Additional Mixer Features"

## Limiter on the Main track is working on every bar
check: the Gain Reduction meter moves whenever the loud parts play
fix: ableton/live-12 §28.24 "Limiter"

## Otherwise
Play the track solo. Distortion that survives with every other track muted is in this
track's chain; distortion that only appears in the full mix is a summing level, not a
device.
