from backend.pv_economics.defaults import MODEL_VERSION, STANDARD_ASSUMPTIONS
from backend.pv_economics.warnings import derive_warnings


def test_standard_assumptions_are_complete_and_versioned():
    values = {item.key: item.value for item in STANDARD_ASSUMPTIONS}
    assert MODEL_VERSION
    assert values["pv_degradation"] == .005
    assert values["battery_rte"] == .9
    assert values["battery_charge_c_rate"] == .5
    assert values["battery_capacity_loss"] == .02
    assert values["projection_years"] == 20
    assert values["electricity_price_growth"] == .02
    assert values["nominal_discount_rate"] == .03
    assert all(item.source for item in STANDARD_ASSUMPTIONS)


def test_warnings_follow_inputs_and_results():
    warnings = derive_warnings(
        profile_kind="h25", has_heat_pump=True, has_ev=True,
        package_only=True, manual_tariff=True, pv_payback=None,
        pv_metrics_available=True,
        battery_metrics_available=True, battery_npv=-1, battery_payback=None,
        warranty_battery=True)
    codes = {item.code for item in warnings}
    assert {"STANDARD_LOAD_PROFILE", "HEAT_PUMP_NOT_MODELLED", "EV_NOT_MODELLED",
            "PACKAGE_PRICE_NOT_SPLIT", "BATTERY_NEGATIVE_NPV",
            "BATTERY_NO_PAYBACK", "PV_NO_PAYBACK",
            "FEED_IN_TARIFF_MANUAL_OVERRIDE", "BATTERY_WARRANTY_IS_BOUNDARY",
            "CALCULATION_ORIENTATION_ONLY"} <= codes


def test_synthetic_profile_warning_is_distinct():
    warnings = derive_warnings(
        profile_kind="exergypulse_daytime", has_heat_pump=False, has_ev=False,
        package_only=False, manual_tariff=False, pv_payback=5,
        pv_metrics_available=True,
        battery_metrics_available=False, battery_npv=None, battery_payback=None,
        warranty_battery=False)
    codes = {item.code for item in warnings}
    assert "SYNTHETIC_LOAD_PROFILE" in codes
    assert "STANDARD_LOAD_PROFILE" not in codes


def test_unavailable_pv_metrics_do_not_claim_no_payback():
    warnings = derive_warnings(
        profile_kind="h25", has_heat_pump=False, has_ev=False,
        package_only=True, manual_tariff=False, pv_metrics_available=False,
        pv_payback=None, battery_metrics_available=False, battery_npv=None,
        battery_payback=None, warranty_battery=False)
    assert "PV_NO_PAYBACK" not in {item.code for item in warnings}
