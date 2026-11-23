// rr6-nx (2026-11-10, the user's options): the language key, from kameo-nx's title_update.cpp (ApplyLanguage,
// SystemLanguage). Ridge Racer 6 reads the console's language (XGetLanguage: the SDK's user_language) and shows its
// text in it; a language it has no text for, it shows in English.
#include "renut_engine/rr6_language.h"

#include <cstring>
#include <string>

#include <rex/cvar.h>
#include <rex/system/flags.h>  // the language key (sdk xam_user.cpp)
#include <rex/logging.h>
#include <rex/platform.h>

#if REX_PLATFORM_SWITCH
#include <switch.h>  // setGetSystemLanguage
#endif

REXCVAR_DECLARE(uint32_t, user_language);  // sdk xam_user.cpp
// rr6-nx (2026-11-22, the sync with the ultimate base): the language key is the base's now (sdk xam_user.cpp, port 177:
// "System" or a name, read by EffectiveLanguage for XGetLanguage; it takes RR6's values too: "auto" counts as the
// console's, the names in any case). ApplyLanguage below still sets user_language from it.

namespace rr6 {

namespace {

// The console's language numbers (XC_LANGUAGE_*).
struct Language {
  const char *name;
  uint32_t xlanguage;
};
constexpr Language kLanguages[] = {
    {"english", 1}, {"japanese", 2}, {"german", 3}, {"french", 4}, {"spanish", 5}, {"italian", 6},
};

// language = "auto": the Switch's system language as one of the names above (setGetSystemLanguage gives "en-US",
// "fr-CA", ...). The others (Portuguese, Dutch, Russian, Korean, Chinese...) and anything a newer firmware adds: English.
const char *SystemLanguage() {
#if REX_PLATFORM_SWITCH
  struct Code {
    const char *code, *name;
  };
  static constexpr Code kCodes[] = {
      {"ja", "japanese"}, {"en-US", "english"}, {"en-GB", "english"}, {"fr", "french"},     {"fr-CA", "french"},
      {"de", "german"},   {"it", "italian"},    {"es", "spanish"},    {"es-419", "spanish"},
  };
  u64 value = 0;
  const Result init = setInitialize();
  if (R_FAILED(init)) {
    REXLOG_WARN("[language] the system language could not be read (0x{:X}): English", init);
    return "english";
  }
  const Result got = setGetSystemLanguage(&value);
  setExit();
  if (R_FAILED(got)) {
    REXLOG_WARN("[language] the system language could not be read (0x{:X}): English", got);
    return "english";
  }
  char code[9] = {};
  std::memcpy(code, &value, 8);
  for (const Code &c : kCodes)
    if (std::strcmp(code, c.code) == 0) {
      REXLOG_INFO("[language] the Switch's system language is {}", code);
      return c.name;
    }
  REXLOG_INFO("[language] the game has no text for the Switch's system language {}: English", code);
#endif
  return "english";
}

}  // namespace

void ApplyLanguage() {
  std::string name = REXCVAR_GET(language);
  for (char &c : name)
    c = (c >= 'A' && c <= 'Z') ? char(c - 'A' + 'a') : c;
  if (name == "auto" || name == "system")
    name = SystemLanguage();
  for (const Language &l : kLanguages) {
    if (name == l.name) {
      REXCVAR_SET(user_language, l.xlanguage);
      REXLOG_INFO("[language] {}: the console's language {}", l.name, l.xlanguage);
      return;
    }
  }
  REXLOG_WARN("[language] language = \"{}\" is not one of the game's: the game stays in English", name);
}

}  // namespace rr6
