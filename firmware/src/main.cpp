#include <Arduino.h>
#include <esp_task_wdt.h>

#include "app/App.h"
#include "app/Settings.h"
#include "app/StartupLogo.h"
#include "hal/PowerSwitch.h"
#include "config.h"
#include "transport/SerialTransport.h"
#include "ui/DisplayManager.h"
#include "util/Log.h"

namespace {

// Longest expected loop() pass is a 512 KB PNG decode (well under a second); 8 s is far from it.
constexpr uint32_t kWatchdogSeconds = 8;

DisplayManager display;
SerialTransport transport;
Settings settings;
StartupLogo logo;
PowerSwitch power;
App app(display, transport, settings, logo, power);

}  // namespace

void setup() {
  LOG_BEGIN();
  LOGF("MiSTerLily %s boot, reset reason %d", MDS_FW_VERSION, (int)esp_reset_reason());

  transport.begin();
  settings.load();
  // First, so a relay held through a reset of this board is taken over without a gap.
  power.begin(settings.powerOn(), settings.autoOn());
  settings.setPowerOn(power.on());
  logo.begin();

  // Without a panel there is nothing to show, but the serial side keeps working.
  if (display.begin(settings.rotated() ? cfg::kRotationFlipped : cfg::kRotationNormal)) {
    app.showStartScreen();
    display.setBrightness(Settings::backlightFor(settings.contrast()));
  }
  app.begin();

  // A stuck loop resets the board; the USB port does not re-enumerate on that reset, and the
  // daemon notices the restart through the uptime in MDSPONG and resends the core.
  esp_task_wdt_init(kWatchdogSeconds, true);
  enableLoopWDT();
}

void loop() {
  app.loop();
  // While a picture arrives, read again at once: each pause caps the speed at 64 bytes per ms.
  if (!app.receiving()) delay(1);
}
