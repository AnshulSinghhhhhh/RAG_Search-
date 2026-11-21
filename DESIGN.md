---
name: Second Brain
description: A calm contact sheet for finding local screenshots, notes, and voice memos.
colors:
  green: "#285d42"
  green-hover: "#1d4832"
  focus: "#589064"
  ink: "#222b26"
  muted: "#64716a"
  paper: "#fff"
  surface: "#f5f7f4"
  line: "#e3e8e3"
  rail: "#182e25"
  rail-muted: "#a7b9ac"
  rail-text: "#c5d1c7"
  rail-active: "#314c3a"
  rail-active-text: "#f0f4e7"
  audio-surface: "#eef2e6"
  audio-ink: "#54633e"
  waveform: "#758d50"
  note-surface: "#edf0f6"
  note-ink: "#44536b"
  error-surface: "#fff5f1"
  error-ink: "#873f2c"
typography:
  headline:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  title:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "-0.025em"
  body:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.875rem"
    lineHeight: 1.85
  summary:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.9375rem"
    lineHeight: 1.6
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.8125rem"
  action:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  text-action:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
  card-title:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
  mono:
    fontFamily: "Consolas, 'Courier New', monospace"
    fontSize: "0.8125rem"
    lineHeight: 1.7
rounded:
  compact: "5px"
  control: "8px"
  button: "9px"
  search: "11px"
  panel: "12px"
  play: "50%"
spacing:
  "4": "4px"
  "8": "8px"
  "12": "12px"
  "16": "16px"
  "20": "20px"
  "24": "24px"
  "30": "30px"
  "44": "44px"
components:
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    typography: "{typography.action}"
    rounded: "{rounded.button}"
    padding: "10px 17px"
  button-primary-hover:
    backgroundColor: "{colors.green-hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.action}"
    rounded: "{rounded.button}"
    padding: "10px 17px"
  button-secondary-hover:
    backgroundColor: "{colors.surface}"
  button-text:
    textColor: "{colors.green}"
    typography: "{typography.text-action}"
    padding: "6px 2px"
  button-icon:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    width: "36px"
    height: "36px"
  search-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.search}"
    padding: "9px 10px 9px 18px"
  navigation:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.rail-text}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  navigation-active:
    backgroundColor: "{colors.rail-active}"
    textColor: "{colors.rail-active-text}"
  suggestion-chip:
    textColor: "#52664d"
    rounded: "{rounded.compact}"
    padding: "5px 9px"
  memory-card:
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
  audio-preview:
    backgroundColor: "{colors.audio-surface}"
    textColor: "{colors.audio-ink}"
    rounded: "{rounded.panel}"
    padding: "35px 25px 23px"
  note-preview:
    backgroundColor: "{colors.note-surface}"
    textColor: "{colors.note-ink}"
    rounded: "{rounded.panel}"
    padding: "29px 24px"
---

# Design System: Second Brain

## Overview

**Creative North Star: "The Local Contact Sheet"**

The Local Contact Sheet makes saved files the visual content. A charcoal-green navigation rail anchors a white workspace; compact type and quiet controls support repeated scanning. DM Sans is bundled locally, keeping this local-first interface visually self-contained.

Flat tonal surfaces identify media and processing states. Images retain their full frame, voice memos use muted sage, and notes use cool grey-blue. The evidence inspector carries the only large structural shadow and entrance animation.

**Key Characteristics:**

- Personal files lead; interface chrome stays restrained.
- Forest-green actions anchor a white workspace and dark navigation rail.
- Media-specific previews share one contact-sheet geometry.
- Original evidence and source locations remain inspectable.

## Colors

### Primary

**Forest action** (`green`, `green-hover`) identifies actions, links, caret, and indexing progress. **Sage focus** (`focus`) marks keyboard focus.

### Secondary

**Audio sage** (`audio-surface`, `audio-ink`, `waveform`) identifies voice memos. **Note mist** (`note-surface`, `note-ink`) identifies text notes. These are media treatments rather than additional action hierarchies.

### Neutral

**Ink**, **muted grey-green**, **paper**, **quiet surface**, and **hairline** (`ink`, `muted`, `paper`, `surface`, `line`) carry text, backgrounds, and separators. **Charcoal green** (`rail`) anchors navigation; `rail-muted`, `rail-text`, `rail-active`, and `rail-active-text` distinguish secondary, ordinary, and current destinations. Warm `error-surface` and `error-ink` distinguish errors from green progress feedback.

**The File First Rule.** Use color to identify an action, state, or media type; let the saved file supply the dominant visual detail.

## Typography

DM Sans with sans-serif fallback serves headings, body, labels, and controls. It loads locally from `secondbrain/web/fonts/DM-Sans.ttf` with swap loading. The root size is 16px; Consolas, Courier New, and monospace serve CLI commands. Frontmatter records the observed role values rather than imposing a new scale.

Headlines are compact and semibold with slight negative tracking. Inspector titles wrap long filenames. Card titles truncate to one line; note titles and bodies each clamp to two complete lines. Evidence text has a 70ch maximum measure; helpers and answer summaries use up to 75ch. Timing and storage figures use tabular numerals where implemented.

**The Evidence Reading Rule.** Keep compact scanning copy in the sheet and readable, wrapping source text in the inspector.

## Layout

Desktop uses a fixed 244px rail, 77px top bar, and offset workspace with 44px horizontal gutters and a 1700px maximum width. The default sheet has three fluid columns with 24px row and 20px column gaps. Cards have no outer shell: preview, filename, metadata, excerpt, and optional match label form one item.

At 1650px the sheet expands to four columns. At 1200px the rail becomes 220px and gutters become 30px. At 1050px the sheet uses two columns. At 850px navigation moves to the top, gutters become 25px, and the recovered width permits three columns. At 650px the sheet uses two columns and filters wrap into separate rows. At 500px it uses one column and larger card text; at 390px gutters become 18px and storage stacks. The CLI guide retains visible wording in compact navigation.

Previews use aspect ratio 1.42, changing to 1.5 below 500px. Audio has a 190px minimum height, reduced to 175px below 850px. Notes retain a 200px minimum height, two-line body clamp, 1.6 leading, and 3.2em body maximum height. The later narrow-preview rule takes precedence over the earlier 390px ratio declaration.

The inspector fills viewport height at the right edge, up to 570px wide or the available viewport. Long paths and evidence wrap. Its horizontal padding changes from 30px to 22px below 650px. Ordinary inputs, folder actions, and import controls wrap with available space.

## Elevation & Depth

Resting cards and controls are flat; tonal grouping, whitespace, and fine borders convey structure. The inspector uses `-16px 0 50px #17231526`; transient toast feedback uses `0 6px 20px #1c322026`.

**The Flat Sheet Rule.** Keep collection cards flat; reserve structural elevation for the inspector and transient feedback.

The inspector enters over 0.2s with ease-out from a 40px horizontal offset and partial opacity. Buttons use 0.15s background transitions; previews use 0.2s transitions and images scale to 1.025 on hover. Reduced motion removes animations and transitions throughout.

## Shapes

Use the established panel radius for previews and inline panels, button radius for full actions, search radius for the broad field, control radius for inputs and navigation, and compact radius for tags and suggestions. Voice play is circular; the inspector has square edges. Outline SVGs normally use 20px dimensions, 1.65 strokes, and rounded caps and joins. Image fitting is contain.

## Components

**Buttons:** primary is forest green with white text; secondary is white with a quiet border; text actions underline on hover. Full buttons have a 44px minimum height. Primary hover deepens green; secondary hover uses the neutral surface. Focus uses a 3px sage outline offset by 3px. Icon actions use compact rounded targets. Disabled actions reduce opacity and show the wait cursor.

**Chips:** suggested queries use compact outlined rectangles, muted green text, and a 30px minimum height. Hover strengthens the border and adds a neutral surface; clicking fills and runs search.

**Cards / Containers:** the preview is the visible container, with no outer card border or shadow. Preview and filename independently open inspection. Images show their whole frame. Voice memos show a decorative waveform, microphone, play affordance, duration, and language. Notes show a file icon and complete clamped lines. Missing images use the implemented neutral fallback. Inline import, progress, notice, and answer containers share restrained tonal grouping.

**Inputs / Fields:** search has a 60px minimum height, fine border, inset icon, expanding input, shortcut hint, and pale-green submit. Focus-within strengthens its border and adds a quiet ring. Path inputs use white fill and the control radius. Preserve native selects and audio controls.

**Navigation:** desktop pairs outline icons and labels on the dark rail; hover lightens a row and the current destination has a stable selected surface. Compact navigation preserves the same destinations. Source-folder management remains available through Folders when the rail source list is hidden.

**Evidence inspector:** a native modal drawer keeps full filename, date, original media, evidence, original-file link, and locations together. Timestamp buttons seek the original recording; transcript qualification stays beside machine-generated audio text. Closing pauses audio and restores opener focus. Escape closes the native dialog; slash focuses search outside editable fields and an open inspector.

## Do's and Don'ts

### Do:

- **Do** use locally served DM Sans and the established compact hierarchy.
- **Do** preserve whole-image previews and media-specific contact-sheet treatments.
- **Do** preserve keyboard focus, complete inspector filenames, and wrapping paths.
- **Do** keep two complete note-body lines within the established preview height.
- **Do** honor reduced motion throughout the interface.

### Don't:

- **Don't** add resting shadows or decorative outer shells to collection cards.
- **Don't** replace saved-file previews with invented collection content.
- **Don't** present the decorative waveform as measured source data.
- **Don't** clip a partial final line into a note preview.
- **Don't** replace the established white workspace and charcoal-green rail identity.
