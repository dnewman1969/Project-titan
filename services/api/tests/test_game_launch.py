"""Direct game launch argv."""

from titan_api.game_launch import game_process_argv


def test_ksp_starts_borderless_so_it_can_be_docked() -> None:
    argv = game_process_argv(r"E:\SteamLibrary\steamapps\common\Kerbal Space Program\KSP_x64.exe")
    assert argv[0].endswith("KSP_x64.exe")
    assert argv[1:] == ["-screen-fullscreen", "0", "-popupwindow"]


def test_non_unity_games_keep_their_own_launcher_args() -> None:
    exe = r"C:\Games\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe"
    assert game_process_argv(exe) == [exe]
