// rr6-nx (2026-11-21, the user: "port over the ingame menu from the ultimate base make sure these options are in the
// config menu ... the language (by default the Switch's), SMAA, the game's MSAA, rumble, the DLC's car Unlock Keys and
// each player's buttons"; "and resolution will change immediately as well"): Ridge Racer 6's rows on the game menu's
// Settings tab (game_menu.h, SetGameMenuRows, the ultimate base's port 227). The base makes the rows of the keys this
// build defines; this changes them to RR6's:
//   - language: RR6's values (config.toml): auto (the Switch's own; the game shows English for a language it has no
//     text for), english, japanese, french, german, spanish, italian. Read at start (*).
//   - msaa_level: off (0) or the game's 2x (2), as config.toml says; from the next frame (the base's port 177's latch,
//     render/surfaces.cpp), taken when the menu closes as the base does.
//   - rr6_dlc_unlock_keys: the 36 car Unlock Key packs in the dlc folder, a row of its own after MSAA (*: the DLC is
//     installed at start). Its text is English in every language (game_menu_text.h has no row for it).
//   - SMAA (banjo_renut_smaa), rumble (input_rumble) and the render heights (handheld, docked) as the base makes them:
//     SMAA and rumble at once, the heights from the next frame on the Switch (the same latch), taken when the menu
//     closes.
// Each player's buttons are the base's P1 to P4 Controls tabs ([input_p1] to [input_p4] in config.toml).
#include <string>
#include <vector>

#include "game_menu.h"
#include "game_menu_text.h"

namespace rr6 {
namespace {

using Setting = blur::GameMenuDialog::Setting;
using Choice = blur::GameMenuDialog::Choice;

Choice Quoted(std::string label, std::string raw) {
  std::string toml = "\"" + raw + "\"";
  return {std::move(label), std::move(raw), std::move(toml)};
}
Choice Plain(std::string label, std::string raw) {
  std::string toml = raw;
  return {std::move(label), std::move(raw), std::move(toml)};
}

void Rows(std::vector<Setting>& rows, int /*language_row*/, const std::string& /*file*/) {
  std::vector<Setting> out;
  out.reserve(rows.size() + 1);
  for (Setting& s : rows) {
    if (s.key == "language") {
      // Each language by its own name (game_menu_text.h's kMenuLanguageNames), the file's value RR6's.
      s.choices = {Quoted(blur::GameMenuText(blur::C_SYSTEM), "auto"), Quoted("English", "english"),
                   Quoted("\xE6\x97\xA5\xE6\x9C\xAC\xE8\xAA\x9E", "japanese"), Quoted("Fran\xC3\xA7" "ais", "french"),
                   Quoted("Deutsch", "german"), Quoted("Espa\xC3\xB1ol", "spanish"), Quoted("Italiano", "italian")};
      s.default_choice = 0;
      s.restart = true;
    } else if (s.key == "msaa_level") {
      s.choices = {Plain(blur::GameMenuText(blur::C_OFF), "0"), Plain("2x", "2")};
      s.default_choice = 0;
      s.restart = false;
      s.apply_on_close = true;
    }
    const bool msaa = s.key == "msaa_level";
    out.push_back(std::move(s));
    if (msaa) {
      Setting dlc;
      dlc.label = "DLC car Unlock Keys";
      dlc.key = "rr6_dlc_unlock_keys";
      dlc.help = "The 36 car Unlock Key packs in the dlc folder next to the game: On unlocks their cars at once. The "
                 "music packs always load.";
      dlc.restart = true;
      dlc.choices = {Plain(blur::GameMenuText(blur::C_ON), "true"), Plain(blur::GameMenuText(blur::C_OFF), "false")};
      dlc.default_choice = 1;
      out.push_back(std::move(dlc));
    }
  }
  rows = std::move(out);
}

}  // namespace

// Once, before the menu is first drawn (renut_app.h, OnCreateDialogs).
void RegisterMenuRows() { blur::SetGameMenuRows(&Rows); }

}  // namespace rr6
