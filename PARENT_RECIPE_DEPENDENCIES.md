# Parent Recipe Repository Dependencies

This document lists all AutoPkg recipe repositories required by the Fleet recipes in this repository. Add these repositories to your AutoPkg installation to use the recipes.

**Note:** This list includes not only the direct parent recipes, but also their parent recipes (the complete dependency chain). For example, many `.pkg` recipes depend on `.download` recipes from other repositories.

## Quick Setup

Run these commands to add all required repositories:

```bash
# Core AutoPkg recipes (most commonly used)
autopkg repo-add recipes

# Third-party recipe repositories (direct parents)
autopkg repo-add homebysix-recipes
autopkg repo-add hjuutilainen-recipes
autopkg repo-add rtrouton-recipes
autopkg repo-add kitzy-recipes
autopkg repo-add amsysuk-recipes
autopkg repo-add datajar-recipes
autopkg repo-add wardsparadox-recipes
autopkg repo-add zentral-recipes
autopkg repo-add ahousseini-recipes
autopkg repo-add jessepeterson-recipes
autopkg repo-add jaharmi-recipes
autopkg repo-add novaksam-recipes
autopkg repo-add swy-recipes
autopkg repo-add Lotusshaney-recipes
autopkg repo-add macprince-recipes

# Additional repositories (parent dependencies)
autopkg repo-add hansen-m-recipes
autopkg repo-add peetinc-recipes
autopkg repo-add almenscorner-recipes
autopkg repo-add valdore86-recipes
```

## Repository Details

### autopkg/recipes
**Repository URL:** https://github.com/autopkg/recipes

**Used by recipes:**
- AutoPkg (AutoPkg.fleet.recipe.yaml)
- BBEdit (BBEdit.fleet.recipe.yaml)
- Cyberduck (Cyberduck.fleet.recipe.yaml)
- Dropbox (Dropbox.fleet.recipe.yaml)
- Evernote (Evernote.fleet.recipe.yaml)
- Google Chrome (GoogleChrome.fleet.recipe.yaml)
- Handbrake (Handbrake.fleet.recipe.yaml)
- OmniDiskSweeper (OmniDiskSweeper.fleet.recipe.yaml)
- OmniFocus (OmniFocus.fleet.recipe.yaml)
- OmniGraffle (OmniGraffle.fleet.recipe.yaml)
- OmniOutliner (OmniOutliner.fleet.recipe.yaml)
- OmniPlan (OmniPlan.fleet.recipe.yaml)
- The Unarchiver (TheUnarchiver.fleet.recipe.yaml)
- Thunderbird (Thunderbird.fleet.recipe.yaml)
- Transmit (Transmit.fleet.recipe.yaml)
- VLC (VLC.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.autopkg.download.AutoPkg-Release`
- `com.github.autopkg.pkg.BBEdit`
- `com.github.autopkg.pkg.Cyberduck`
- `com.github.autopkg.pkg.Evernote`
- `com.github.autopkg.pkg.Handbrake`
- `com.github.autopkg.pkg.OmniDiskSweeper`
- `com.github.autopkg.pkg.TheUnarchiver`
- `com.github.autopkg.pkg.Thunderbird`
- `com.github.autopkg.pkg.VLC`
- `com.github.autopkg.pkg.dropbox`
- `com.github.autopkg.pkg.googlechrome`
- `com.github.autopkg.pkg.omnifocus`
- `com.github.autopkg.pkg.omnigraffle`
- `com.github.autopkg.pkg.omnioutliner`
- `com.github.autopkg.pkg.omniplan`
- `com.github.autopkg.pkg.transmit`

---

### autopkg/homebysix-recipes
**Repository URL:** https://github.com/autopkg/homebysix-recipes

**Used by recipes:**
- Caffeine (Caffeine.fleet.recipe.yaml)
- Docker Desktop (DockerDesktop.fleet.recipe.yaml)
- GitHub CLI (GitHubCLI.fleet.recipe.yaml)
- GitHub Desktop (GithubDesktop.fleet.recipe.yaml)
- MeetingBar (MeetingBar.fleet.recipe.yaml)
- Recipe Robot (RecipeRobot.fleet.recipe.yaml)
- Zoom (Zoom.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.homebysix.pkg.Caffeine`
- `com.github.homebysix.pkg.DockerDesktop`
- `com.github.homebysix.pkg.GitHubCLI`
- `com.github.homebysix.pkg.GitHubDesktop`
- `com.github.homebysix.pkg.MeetingBar`
- `com.github.homebysix.pkg.RecipeRobot`
- `com.github.homebysix.pkg.Zoom`

---

### autopkg/hjuutilainen-recipes
**Repository URL:** https://github.com/autopkg/hjuutilainen-recipes

**Used by recipes:**
- 1Password 8 (1Password8.fleet.recipe.yaml)
- iTerm2 (iTerm2.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `io.github.hjuutilainen.pkg.1Password8`
- `io.github.hjuutilainen.pkg.iTerm2`

---

### autopkg/rtrouton-recipes
**Repository URL:** https://github.com/autopkg/rtrouton-recipes

**Used by recipes:**
- Firefox (Firefox.fleet.recipe.yaml)
- Slack (Slack.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.rtrouton.pkg.Firefox`
- `com.github.rtrouton.pkg.SlackAppleSilicon`

---

### autopkg/kitzy-recipes
**Repository URL:** https://github.com/autopkg/kitzy-recipes

**Used by recipes:**
- Claude (Claude.fleet.recipe.yaml)
- Elgato Stream Deck (ElgatoStreamDeck.fleet.recipe.yaml)
- fleetctl (fleetctl.fleet.recipe.yaml)
- GPG Suite (GPGSuite.fleet.recipe.yaml)
- Icon Grabber (IconGrabber.fleet.recipe.yaml)
- Munki Tools (MunkiTools.fleet.recipe.yaml)
- Raycast (Raycast.fleet.recipe.yaml)
- Unblocked (Unblocked.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.kitzy.download.Unblocked`
- `com.github.kitzy.download.icongrabber`
- `com.github.kitzy.download.munkitools`
- `com.github.kitzy.pkg.Claude`
- `com.github.kitzy.pkg.ElgatoStreamDeck`
- `com.github.kitzy.pkg.GPGSuite`
- `com.github.kitzy.pkg.Raycast`
- `com.github.kitzy.pkg.fleetctl`

---

### autopkg/amsysuk-recipes
**Repository URL:** https://github.com/autopkg/amsysuk-recipes

**Used by recipes:**
- Visual Studio Code (VisualStudioCode.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.amsysuk-recipes.pkg.VisualStudioCode`

---

### autopkg/datajar-recipes
**Repository URL:** https://github.com/autopkg/datajar-recipes

**Used by recipes:**
- Postman (Postman.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.dataJAR-recipes.pkg.postman`

---

### autopkg/wardsparadox-recipes
**Repository URL:** https://github.com/autopkg/wardsparadox-recipes

**Used by recipes:**
- Ghostty (Ghostty.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.autopkg.wardsparadox.pkg.Ghostty`

---

### autopkg/zentral-recipes
**Repository URL:** https://github.com/autopkg/zentral-recipes

**Used by recipes:**
- Santa (NorthPoleSecSanta.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.autopkg.zentral.download.santa`

---

### autopkg/ahousseini-recipes
**Repository URL:** https://github.com/autopkg/ahousseini-recipes

**Used by recipes:**
- UTM (UTM.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.ahousseini-recipes.pkg.UTM`

---

### autopkg/jessepeterson-recipes
**Repository URL:** https://github.com/autopkg/jessepeterson-recipes

**Used by recipes:**
- dockutil (dockutil.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.autopkg.jessepeterson.download.dockutil`

---

### autopkg/jaharmi-recipes
**Repository URL:** https://github.com/autopkg/jaharmi-recipes

**Used by recipes:**
- Signal (Signal.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.jaharmi.pkg.Signal`

---

### autopkg/novaksam-recipes
**Repository URL:** https://github.com/autopkg/novaksam-recipes

**Used by recipes:**
- Suspicious Package (SuspiciousPackage.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.novaksam.pkg.SuspiciousPackage`

---

### autopkg/swy-recipes
**Repository URL:** https://github.com/autopkg/swy-recipes

**Used by recipes:**
- Notion (Notion.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.swy.pkg.Notion`

---

### autopkg/Lotusshaney-recipes
**Repository URL:** https://github.com/autopkg/Lotusshaney-recipes

**Used by recipes:**
- Glean (Glean.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.Lotusshaney.pkg.Glean`

---

### autopkg/hansen-m-recipes
**Repository URL:** https://github.com/autopkg/hansen-m-recipes

**Dependency Type:** Parent of parent (download recipes)

**Used as parent by:**
- `com.github.homebysix.pkg.Zoom` (Zoom.fleet.recipe.yaml)

---

### autopkg/peetinc-recipes
**Repository URL:** https://github.com/autopkg/peetinc-recipes

**Dependency Type:** Parent of parent (download recipes)

**Used as parent by:**
- `com.github.homebysix.pkg.Caffeine` (Caffeine.fleet.recipe.yaml)

---

### autopkg/almenscorner-recipes
**Repository URL:** https://github.com/autopkg/almenscorner-recipes

**Dependency Type:** Parent of parent (download recipes)

**Used as parent by:**
- `com.github.kitzy.pkg.Claude` (Claude.fleet.recipe.yaml)

---

### autopkg/valdore86-recipes
**Repository URL:** https://github.com/autopkg/valdore86-recipes

**Dependency Type:** Parent of parent (download recipes)

**Used as parent by:**
- `com.github.amsysuk-recipes.pkg.VisualStudioCode` (VisualStudioCode.fleet.recipe.yaml)

---

### autopkg/macprince-recipes
**Repository URL:** https://github.com/autopkg/macprince-recipes

**Used by recipes:**
- Tailscale (Tailscale.fleet.recipe.yaml)

**Parent recipe identifiers:**
- `com.github.macprince.pkg.Tailscale`

## Summary

- **Total repositories required:** 20
  - **Direct parent repositories:** 16
  - **Parent dependency repositories:** 4 (hansen-m, peetinc, almenscorner, valdore86)
- **Total parent recipes used:** 47
- **Most used repository:** autopkg/recipes (16 recipes)

## Repository Dependency Chain

Many recipes have a dependency chain like this:
```
Fleet Recipe (.fleet.recipe.yaml)
  ↓
Parent .pkg recipe (in one repository)
  ↓
Parent .download recipe (may be in a different repository)
```

For example:
- **Claude.fleet.recipe.yaml** → `com.github.kitzy.pkg.Claude` (kitzy-recipes) → `Claude.download` (almenscorner-recipes)
- **Zoom.fleet.recipe.yaml** → `com.github.homebysix.pkg.Zoom` (homebysix-recipes) → `Zoom.download` (hansen-m-recipes)
- **Caffeine.fleet.recipe.yaml** → `com.github.homebysix.pkg.Caffeine` (homebysix-recipes) → `Caffeine.download` (peetinc-recipes)
- **VisualStudioCode.fleet.recipe.yaml** → `com.github.amsysuk-recipes.pkg.VisualStudioCode` (amsysuk-recipes) → `VisualStudioCode.download` (valdore86-recipes)

## Maintenance Notes

This document should be updated when:
- New recipes are added to this repository
- Parent recipes are changed in existing recipes
- Recipe repositories are reorganized or moved

Last updated: January 28, 2026
