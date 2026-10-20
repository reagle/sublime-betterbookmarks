# Notes: survive-external-edits

Working notes for this branch (Joseph Reagle, October 2026). **Delete this file before opening a PR upstream.**

## Problem

Better Bookmarks marks kept disappearing on my machines (hom and wor, synced with unison). Not moving --- disappearing.

## Why marks disappear in the original plugin

The plugin never removes a mark because it is "in the wrong place"; stale offsets only misplace marks. Marks vanish only when the cache file (`Packages/User/BetterBookmarks/<md5 of path>.bb_cache`) is deleted, overwritten by a view holding fewer marks, or never loaded into the view.

1. **Delete on close (likely main cause).** With the default `cleanup_empty_cache_on_close: true`, closing a view with no marks deletes its cache. A view can look marked but hold no marks: the per-layer regions were not `PERSISTENT`, so after a restart only the gutter icons came back. Closing (or adding a mark, which re-renders from the empty layer) then lost them. Same if the document was open before its cache arrived via sync. Unison then propagates the deletion.
2. **Offsets go stale.** Marks were stored only as character offsets, so edits made elsewhere (another machine, git, a formatter) shift them to wrong positions.
3. **Stale view overwrites a newer cache.** A document open on both machines: saving on the one with older in-memory marks overwrites the cache, and `prefer = newer` propagates it. **Deliberately not fixed:** last save wins, as in most editors; the plugin should not know about syncing.

## What the branch changes

- Each mark is stored as `[a, b, anchor_a, anchor_b]`, where an anchor is `{"line", "col", "text"}`. On load, use the saved line if its text still matches, else the nearest line with identical text, else the saved line number; then the saved column. Character precision within a line is kept.
- The leading offsets keep the cache readable by the original plugin; old offset-only caches still load.
- An empty cache is written, or deleted on close, only after this view has loaded its marks this session (`Loaded` set).
- Mark regions are `PERSISTENT`, so they survive in the session.
- The cache is written as soon as marks change (if `cache_marks_on_save`), so removing the last mark sticks.
- Marks are re-read on `on_reload` (ST4; file changed on disk) and on first activation of a session-restored view.
- All documented settings still behave as described.

Known limit: if the bookmarked line's own text is edited and lines also move above it, the mark falls back to the old line number. A fuzzy "most similar nearby line" match could improve this.

## Testing (started 2026-10-20)

Only mock-tested so far. Installed on my machines as an override: `~/Library/Application Support/Sublime Text/Packages/Better Bookmarks/BetterBookmarks.py` (synced by unison). Delete that folder once a fixed release reaches Package Control.

Checks to do over a few weeks of normal use:

- [ ] Bookmark something, quit Sublime, reopen; close the document, reopen it --- mark still there.
- [ ] Add lines above a mark on one machine, sync --- mark on the same line on the other.
- [ ] Remove the last mark in a document, close and reopen --- it stays gone.

## Next step, if it holds up

Upstream (`dusk125/sublime-betterbookmarks`) was archived 2025-01-16, but the package is still listed in Package Control (`repository/b.json`). The community org github.com/SublimeText adopts abandoned packages (TrailingSpaces, AdvancedNewFile, PlainTasks...). Ask on their Discord (https://discord.gg/D43Pecu) for adoption, then a channel PR repoints the package. Draft message:

> Hi all, I'd like to propose adopting **Better Bookmarks** (Package Control: "Better Bookmarks", https://github.com/dusk125/sublime-betterbookmarks). The repo was archived by its owner in January 2025, but the package is still listed in the channel. I have a fix for a long-standing data-loss problem: bookmarks were cached only as character offsets, so they drifted or vanished whenever a file changed outside Sublime (git, formatters, sync tools). An empty cache could also overwrite or delete real marks if a view's marks hadn't been restored. The fix stores line text anchors after the existing offsets, so it stays readable by the current version and old caches still load. The branch is here: https://github.com/reagle/sublime-betterbookmarks/tree/survive-external-edits. Would the org take it in, either by forking or by asking dusk125 to transfer it, and repoint the channel entry? I'm happy to land this fix and help maintain it.
