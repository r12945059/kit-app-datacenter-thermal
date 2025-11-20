# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

import omni.ext
import omni.ui as ui
import omni.usd
from pxr import Usd, Sdf, Gf
# Functions and vars are available to other extensions as usual in python:
# `my_company.my_python_ui_extension.some_public_function(x)`
def some_public_function(x: int):
    """This is a public function that can be called from other extensions."""
    print(f"[my_company.my_python_ui_extension] some_public_function was called with {x}")
    return x ** x


# Any class derived from `omni.ext.IExt` in the top level module (defined in
# `python.modules` of `extension.toml`) will be instantiated when the extension
# gets enabled, and `on_startup(ext_id)` will be called. Later when the
# extension gets disabled on_shutdown() is called.
class MyExtension(omni.ext.IExt):
        """
    機房「氣冷顯熱守恆」可視化 Extension

    模式：
      - 設計模式：輸入 rackPowerW + 目標 ΔT，計算所需 m。
      - 稽核模式：輸入 rackPowerW + mdotActual，計算 ΔT_actual 並依目標 ΔT 上色。

    USD 自訂屬性：
      - user:rackPowerW (double, W)                 # 必填
      - user:mdotActual (double, kg/s)              # 稽核模式用，可留空
      - user:mdotRequired (double, kg/s)            # 設計模式運算結果

    顏色覆蓋：
      - 綠：ΔT < 目標
      - 黃：ΔT ≈ 目標
      - 紅：ΔT > 目標
      - 可一鍵啟用/停用覆蓋
    """
    # ext_id is the current extension id. It can be used with the extension
    # manager to query additional information, like where this extension is
    # located on the filesystem.
    def on_startup(self, ext_id):
        """This is called every time the extension is activated."""
        print("[my_company.my_python_ui_extension] Extension startup")
        self._ext_id = ext_id
        # 顏色覆蓋用的原始顏色 cache
        self._orig_colors = {}  # {prim_path: color_array or None}
        self._color_override_enabled_model = ui.SimpleBoolModel(True)

        # cp & ΔT 模型
        self._cp_model = ui.SimpleFloatModel(1005.0)   # 空氣 cp 近似值
        self._target_dt_model = ui.SimpleFloatModel(10.0)  # 目標 ΔT

        # 模式：0 = 設計模式, 1 = 稽核模式
        self._mode_model = ui.SimpleIntModel(1)  # 預設：稽核模式

        # 批次填寫用
        self._batch_power_model = ui.SimpleFloatModel(1000.0)
        self._batch_mdot_model = ui.SimpleFloatModel(0.1)

        # 建 UI 視窗
        self._window = ui.Window(
            "Rack Thermal Visualization", width=400, height=400
        )

    def on_shutdown(self):
        """This is called every time the extension is deactivated. It is used
        to clean up the extension state."""
        print("[my_company.my_python_ui_extension] Extension shutdown")
        self._restore_colors()
        self._window = None
    # -------------------------------
    # UI 建構
    # -------------------------------
    def _build_ui(self):
        with self._window.frame:
            with ui.VStack(spacing=8, height=0):

                ui.Label("機房氣冷顯熱守恆可視化", style={"font_size": 18})

                # 模式切換
                with ui.HStack(spacing=4):
                    ui.Label("模式：")
                    ui.ComboBox(
                        self._mode_model,
                        "設計模式 (P + 目標 ΔT → ṁ)",
                        "稽核模式 (P + mdotActual → ΔT)",
                    )

                # 物性與目標 ΔT
                with ui.CollapsableFrame("參數設定", collapsed=False):
                    with ui.VStack(spacing=4, height=0):
                        with ui.HStack():
                            ui.Label("cp：", width=150)
                            ui.FloatField(self._cp_model)
                        with ui.HStack():
                            ui.Label("目標：", width=150)
                            ui.FloatField(self._target_dt_model)

                # 批次填寫 USD 屬性（目前選取的 rack）
                with ui.CollapsableFrame("批次填寫選取 rack 屬性", collapsed=False):
                    with ui.VStack(spacing=4, height=0):
                        with ui.HStack():
                            ui.Label("rackPowerW (W)：", width=150)
                            ui.FloatField(self._batch_power_model)
                        with ui.HStack():
                            ui.Label("mdotActual (kg/s)：", width=150)
                            ui.FloatField(self._batch_mdot_model)

                        ui.Button(
                            "套用到目前選取的 prim",
                            clicked_fn=self._apply_defaults_to_selection,
                        )

                # 顏色覆蓋控制
                with ui.CollapsableFrame("顏色視覺化控制", collapsed=False):
                    with ui.VStack(spacing=4, height=0):
                        ui.CheckBox(
                            "啟用顏色覆蓋 (不影響屬性值)",
                            model=self._color_override_enabled_model,
                        )

                        ui.Button(
                            "重新計算並更新顏色",
                            clicked_fn=self._recompute_and_color,
                        )

                ui.Spacer(height=10)
                ui.Label(
                    "說明：\n"
                    "• 只要 prim 上有 user:rackPowerW（W）就會被納入計算。\n"
                    "• 設計模式：依 P 與目標 ΔT 計算所需質量流率，寫入 user:mdotRequired。\n"
                    "• 稽核模式：使用 user:mdotActual 計算 ΔT 並依目標值上色。",
                    word_wrap=True,
                )

        # 變更參數時自動重算
        self._cp_model.add_value_changed_fn(lambda m: self._recompute_and_color())
        self._target_dt_model.add_value_changed_fn(
            lambda m: self._recompute_and_color()
        )
        self._mode_model.add_value_changed_fn(lambda m: self._recompute_and_color())
        self._color_override_enabled_model.add_value_changed_fn(
            lambda m: self._recompute_and_color()
        )

    # -------------------------------
    # 工具函式
    # -------------------------------
    def _get_stage(self):
        ctx = omni.usd.get_context()
        return ctx.get_stage()

    # 批次將 UI 中的預設 P / mdot 寫入「目前選取」的 prim
    def _apply_defaults_to_selection(self):
        stage = self._get_stage()
        if stage is None:
            print("[rack_thermal] No USD stage loaded.")
            return

        selection = omni.usd.get_context().get_selection()
        paths = selection.get_selected_prim_paths()

        power_val = self._batch_power_model.get_value_as_float()
        mdot_val = self._batch_mdot_model.get_value_as_float()

        for path in paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            # rackPowerW
            if power_val is not None:
                attr_p = prim.GetAttribute("user:rackPowerW")
                if not attr_p:
                    attr_p = prim.CreateAttribute(
                        "user:rackPowerW",
                        Sdf.ValueTypeNames.Double,
                        custom=True,
                    )
                attr_p.Set(float(power_val))

            # mdotActual
            if mdot_val is not None:
                attr_m = prim.GetAttribute("user:mdotActual")
                if not attr_m:
                    attr_m = prim.CreateAttribute(
                        "user:mdotActual",
                        Sdf.ValueTypeNames.Double,
                        custom=True,
                    )
                attr_m.Set(float(mdot_val))

        print(
            f"[rack_thermal] Applied defaults to {len(paths)} prim(s): "
            f"rackPowerW={power_val}, mdotActual={mdot_val}"
        )

        # 屬性變了，重算一次
        self._recompute_and_color()

    # 主計算邏輯：走過 stage 上所有有 user:rackPowerW 的 prim
    def _recompute_and_color(self):
        stage = self._get_stage()
        if stage is None:
            return

        cp = max(self._cp_model.get_value_as_float(), 1e-6)
        target_dt = self._target_dt_model.get_value_as_float()
        mode = self._mode_model.get_value_as_int()
        enable_override = self._color_override_enabled_model.get_value_as_bool()

        # 若關閉顏色覆蓋，就恢復原色後直接 return
        if not enable_override:
            self._restore_colors()
            return

        # 開啟覆蓋時先清掉舊的顏色紀錄，重新 cache
        self._orig_colors = {}

        for prim in stage.Traverse():
            if not prim.IsValid():
                continue

            attr_p = prim.GetAttribute("user:rackPowerW")
            if not attr_p or not attr_p.HasAuthoredValue():
                continue

            try:
                power_w = float(attr_p.Get())
            except Exception:
                continue

            if power_w <= 0.0:
                continue

            if mode == 0:
                # 設計模式：P + 目標 ΔT → 所需 mdot
                if target_dt <= 0.0:
                    continue
                m_required = power_w / (cp * target_dt)

                # 寫入 user:mdotRequired
                attr_m_req = prim.GetAttribute("user:mdotRequired")
                if not attr_m_req:
                    attr_m_req = prim.CreateAttribute(
                        "user:mdotRequired",
                        Sdf.ValueTypeNames.Double,
                        custom=True,
                    )
                attr_m_req.Set(float(m_required))

                # 顏色用目標 ΔT
                delta_t = target_dt

            else:
                # 稽核模式：P + mdotActual → ΔT
                attr_m = prim.GetAttribute("user:mdotActual")
                if not attr_m or not attr_m.HasAuthoredValue():
                    continue

                try:
                    mdot = float(attr_m.Get())
                except Exception:
                    continue

                if mdot <= 0.0:
                    continue

                delta_t = power_w / (cp * mdot)

            # 依 ΔT 相對於目標值上色
            self._apply_color_for_prim(prim, delta_t, target_dt)

    def _apply_color_for_prim(self, prim: Usd.Prim, delta_t: float, target_dt: float):
        path = str(prim.GetPath())
        stage = self._get_stage()
        if stage is None:
            return

        # Cache 原本的 displayColor（只存一次）
        if path not in self._orig_colors:
            color_attr = prim.GetAttribute("primvars:displayColor")
            if color_attr and color_attr.HasAuthoredValue():
                self._orig_colors[path] = color_attr.Get()
            else:
                self._orig_colors[path] = None

        # 設定新顏色
        tol = 1e-3
        if target_dt <= 0.0:
            color = Gf.Vec3f(0.5, 0.5, 0.5)
        else:
            if delta_t < (target_dt - tol):
                color = Gf.Vec3f(0.0, 1.0, 0.0)   # 綠
            elif abs(delta_t - target_dt) <= tol:
                color = Gf.Vec3f(1.0, 1.0, 0.0)   # 黃
            else:
                color = Gf.Vec3f(1.0, 0.0, 0.0)   # 紅

        color_attr = prim.GetAttribute("primvars:displayColor")
        if not color_attr:
            color_attr = prim.CreateAttribute(
                "primvars:displayColor",
                Sdf.ValueTypeNames.Color3fArray,
                custom=False,
            )

        color_attr.Set([color])

    def _restore_colors(self):
        """將所有被覆蓋的 rack 顏色恢復成啟用前的值。"""
        stage = self._get_stage()
        if stage is None:
            return

        for path, orig in self._orig_colors.items():
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                continue

            color_attr = prim.GetAttribute("primvars:displayColor")

            if orig is None:
                if color_attr:
                    prim.RemoveProperty("primvars:displayColor")
            else:
                if not color_attr:
                    color_attr = prim.CreateAttribute(
                        "primvars:displayColor",
                        Sdf.ValueTypeNames.Color3fArray,
                        custom=False,
                    )
                color_attr.Set(orig)

        self._orig_colors = {}
