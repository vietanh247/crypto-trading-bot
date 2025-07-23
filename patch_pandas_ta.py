# patch_pandas_ta.py
import sys
import pandas_ta.momentum.squeeze_pro

# Fix lỗi import
if 'NaN' not in sys.modules:
    from numpy import nan as NaN
    sys.modules['NaN'] = NaN

# Apply patch
import pandas_ta.momentum.squeeze_pro