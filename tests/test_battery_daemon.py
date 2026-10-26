"""system/battery/j701f-battery: one round of the loop against a fake sysfs tree."""
import os
import pathlib
import subprocess
import tempfile
import time
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "system/battery/j701f-battery"


class BatteryDaemon(unittest.TestCase):
    def run_round(self, *, cap, mv, ma, reg="0x10", online=1, temp=25000, usb="Unknown [SDP] DCP CDP",
                  inlim=500, chg=450, hwmon=True, behaviour="[auto] inhibit-charge", then=None, conf=None):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            dev = d / "devices/1-003b"
            dev.mkdir(parents=True)
            fg, ch, hw = d / "fg", d / "chg", d / "hwmon/hwmon3"
            for x in (fg, ch, hw):
                x.mkdir(parents=True)
            (fg / "device").symlink_to(dev)
            (fg / "capacity").write_text(f"{cap}\n")
            (fg / "voltage_avg").write_text(f"{mv * 1000}\n")
            (fg / "current_avg").write_text(f"{ma * 1000}\n")
            (ch / "online").write_text(f"{online}\n")
            (ch / "usb_type").write_text(usb + "\n")
            (ch / "input_current_limit").write_text(f"{inlim * 1000}\n")
            (ch / "constant_charge_current").write_text(f"{chg * 1000}\n")
            if behaviour:
                (ch / "charge_behaviour").write_text(behaviour + "\n")
            if hwmon:
                (hw / "name").write_text("j701f_adc\n")
                (hw / "temp1_input").write_text(f"{temp}\n")
            log = d / "i2c.log"
            (d / "i2cget").write_text(f"#!/bin/sh\necho {reg}\n")
            (d / "i2cset").write_text(f"#!/bin/sh\necho \"$@\" >> {log}\n")
            for x in ("i2cget", "i2cset"):
                (d / x).chmod(0o755)
            (d / "battery.conf").write_text(conf or "")
            env = dict(os.environ, J701F_CONF=str(d / "battery.conf"), J701F_FG=str(fg), J701F_CHG=str(ch), J701F_HWMON=str(d / "hwmon"),
                       J701F_I2CSET=str(d / "i2cset"), J701F_I2CGET=str(d / "i2cget"))
            if then is None:
                subprocess.run(["sh", str(SCRIPT), "0", "1"], env=env, check=True, timeout=20)
            else:   # a second round one second later, after the test changed some files
                proc = subprocess.Popen(["sh", str(SCRIPT), "1", "2"], env=env)
                time.sleep(0.5)
                for name, text in then.items():
                    target = {"temp": hw / "temp1_input", "online": ch / "online", "cap": fg / "capacity",
                              "conf": d / "battery.conf"}[name]
                    target.write_text(f"{text}\n")
                self.assertEqual(proc.wait(timeout=20), 0)
            return {
                "i2c": log.read_text().split("\n")[:-1] if log.exists() else [],
                "in": int((ch / "input_current_limit").read_text()) // 1000,
                "chg": int((ch / "constant_charge_current").read_text()) // 1000,
                "behaviour": (ch / "charge_behaviour").read_text().strip() if behaviour else None,
            }

    def test_full_battery_in_current_mode_goes_to_voltage_mode(self):
        r = self.run_round(cap=43, mv=4347, ma=195)
        self.assertEqual(r["i2c"], ["-f -y 1 0x3b 0x4a 0xff"])

    def test_mid_charge_stays_in_current_mode(self):
        self.assertEqual(self.run_round(cap=60, mv=4100, ma=400)["i2c"], [])

    def test_discharging_below_97_leaves_high_voltage_mode(self):
        r = self.run_round(cap=90, mv=4150, ma=-300, reg="0xff", online=0)
        self.assertEqual(r["i2c"], ["-f -y 1 0x3b 0x4a 0x10"])

    def test_still_charging_keeps_high_voltage_mode(self):
        self.assertEqual(self.run_round(cap=60, mv=4347, ma=190, reg="0xff")["i2c"], [])

    def test_nearly_empty_goes_to_voltage_mode(self):
        r = self.run_round(cap=5, mv=3500, ma=-200, online=0)  # load-corrected: 3560 mV
        self.assertEqual(r["i2c"], ["-f -y 1 0x3b 0x4a 0xff"])

    def test_computer_port_limits_untouched_at_room_temperature(self):
        r = self.run_round(cap=60, mv=4000, ma=300)
        self.assertEqual((r["in"], r["chg"]), (500, 450))

    def test_wall_charger_raised_at_room_temperature(self):
        r = self.run_round(cap=60, mv=4000, ma=900, usb="Unknown SDP [DCP] CDP", inlim=1200, chg=1000)
        self.assertEqual((r["in"], r["chg"]), (1550, 1500))

    def test_wall_charger_not_raised_without_temperature(self):
        r = self.run_round(cap=60, mv=4000, ma=900, usb="Unknown SDP [DCP] CDP", inlim=1200, chg=1000, hwmon=False)
        self.assertEqual((r["in"], r["chg"]), (1200, 1000))

    def test_wall_charger_lowered_when_cool_hot_and_too_hot(self):
        for temp, want in ((12000, 700), (3000, 450), (43000, 450)):
            with self.subTest(temp=temp):
                r = self.run_round(cap=60, mv=4000, ma=900, usb="Unknown SDP [DCP] CDP", inlim=1200, chg=1000, temp=temp)
                self.assertEqual(r["chg"], want)
                self.assertEqual(r["in"], 1200)

    def test_computer_port_lowered_only_when_too_hot_or_cold(self):
        self.assertEqual(self.run_round(cap=60, mv=4000, ma=300, temp=12000)["chg"], 450)
        r = self.run_round(cap=60, mv=4000, ma=300, temp=52000)
        self.assertEqual((r["chg"], r["behaviour"]), (450, "inhibit-charge"))

    def test_too_hot_or_too_cold_switches_charging_off(self):
        for temp in (52000, -2000):
            with self.subTest(temp=temp):
                r = self.run_round(cap=60, mv=4000, ma=900, usb="Unknown SDP [DCP] CDP", inlim=1200, chg=1000, temp=temp)
                self.assertEqual(r["behaviour"], "inhibit-charge")

    def test_too_hot_without_behaviour_file_falls_back_to_minimum_current(self):
        r = self.run_round(cap=60, mv=4000, ma=300, temp=52000, behaviour=None)
        self.assertEqual(r["chg"], 100)

    def test_charging_comes_back_when_the_battery_has_cooled(self):
        r = self.run_round(cap=60, mv=4000, ma=300, temp=52000, then={"temp": 44000})
        self.assertEqual(r["behaviour"], "auto")

    def test_charging_stays_off_while_still_above_the_recovery_point(self):
        r = self.run_round(cap=60, mv=4000, ma=300, temp=52000, then={"temp": 47000})
        self.assertEqual(r["behaviour"], "inhibit-charge")

    def test_charging_comes_back_when_the_cable_is_pulled(self):
        r = self.run_round(cap=60, mv=4000, ma=300, temp=52000, then={"online": 0})
        self.assertEqual(r["behaviour"], "auto")

    def test_charge_limit_stops_at_the_limit_and_not_below(self):
        self.assertEqual(self.run_round(cap=80, mv=4100, ma=300, conf="charge_limit=80\n")["behaviour"], "inhibit-charge")
        self.assertEqual(self.run_round(cap=79, mv=4100, ma=300, conf="charge_limit=80\n")["behaviour"],
                         "[auto] inhibit-charge")

    def test_charge_limit_resumes_five_points_below(self):
        r = self.run_round(cap=80, mv=4100, ma=300, conf="charge_limit=80\n", then={"cap": 77})
        self.assertEqual(r["behaviour"], "inhibit-charge")
        r = self.run_round(cap=80, mv=4100, ma=300, conf="charge_limit=80\n", then={"cap": 75})
        self.assertEqual(r["behaviour"], "auto")

    def test_charge_limit_removed_resumes(self):
        r = self.run_round(cap=90, mv=4200, ma=300, conf="charge_limit=80\n", then={"conf": ""})
        self.assertEqual(r["behaviour"], "auto")

    def test_charge_limit_works_without_a_temperature_reading(self):
        r = self.run_round(cap=85, mv=4200, ma=300, conf="charge_limit=80\n", hwmon=False)
        self.assertEqual(r["behaviour"], "inhibit-charge")

    def test_nonsense_in_the_configuration_is_no_limit(self):
        for conf in ("charge_limit=5\n", "charge_limit=abc\n", "charge_limit=800\n", "# charge_limit=80\n"):
            with self.subTest(conf=conf):
                self.assertEqual(self.run_round(cap=95, mv=4300, ma=300, conf=conf)["behaviour"], "[auto] inhibit-charge")

    def test_somebody_elses_inhibit_is_left_alone(self):
        r = self.run_round(cap=60, mv=4000, ma=0, behaviour="auto [inhibit-charge]")
        self.assertEqual(r["behaviour"], "auto [inhibit-charge]")

    def test_no_cable_no_limit_writes(self):
        r = self.run_round(cap=60, mv=3900, ma=-300, online=0, temp=52000)
        self.assertEqual((r["in"], r["chg"]), (500, 450))


if __name__ == "__main__":
    unittest.main()
