// rr6-nx (2026-11-10, the user's options; kameo-nx's language key): the game's language from config.toml.
#pragma once

namespace rr6 {

// language = "auto" (the Switch's system language; English elsewhere, and when the game has none for it), or english,
// japanese, french, german, spanish, italian: sets the SDK's user_language, the console language the game reads
// (XGetLanguage). Called once the config is loaded, before the game starts (src/renut_app.h, OnPostSetup).
void ApplyLanguage();

}  // namespace rr6
