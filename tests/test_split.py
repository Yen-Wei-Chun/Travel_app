from modules.split import calculate_splits

def test_aa():
    result = calculate_splits(1000, ["小明", "小華", "小美"], "AA")
    assert sum(result.values()) == 1000
    print("AA 測試通過：", result)

def test_ratio():
    result = calculate_splits(1000, ["小明", "小華"], "比例",
                              weights={"小明": 2, "小華": 1})
    assert sum(result.values()) == 1000
    print("比例測試通過：", result)

def test_custom():
    result = calculate_splits(1000, ["小明", "小華"], "指定",
                              weights={"小明": 700, "小華": 300})
    assert sum(result.values()) == 1000
    print("指定測試通過：", result)

def test_single():
    result = calculate_splits(500, ["小明"], "AA")
    assert result["小明"] == 500
    print("單人測試通過：", result)

if __name__ == "__main__":
    test_aa()
    test_ratio()
    test_custom()
    test_single()
    print("全部測試通過 ✓")