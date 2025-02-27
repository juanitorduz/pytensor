import re

import numpy as np
import pytest

import pytensor
import pytensor.tensor as pt
from pytensor import config
from tests.link.numba.test_basic import compare_numba_and_py


numba = pytest.importorskip("numba")

ATOL = 0 if config.floatX.endswith("64") else 1e-6
RTOL = 1e-7 if config.floatX.endswith("64") else 1e-6
rng = np.random.default_rng(42849)


def transpose_func(x, trans):
    if trans == 0:
        return x
    if trans == 1:
        return x.conj().T
    if trans == 2:
        return x.T


@pytest.mark.parametrize(
    "b_func, b_size",
    [(pt.matrix, (5, 1)), (pt.matrix, (5, 5)), (pt.vector, (5,))],
    ids=["b_col_vec", "b_matrix", "b_vec"],
)
@pytest.mark.parametrize("lower", [True, False], ids=["lower=True", "lower=False"])
@pytest.mark.parametrize("trans", [0, 1, 2], ids=["trans=N", "trans=C", "trans=T"])
@pytest.mark.parametrize(
    "unit_diag", [True, False], ids=["unit_diag=True", "unit_diag=False"]
)
@pytest.mark.parametrize("complex", [True, False], ids=["complex", "real"])
@pytest.mark.filterwarnings(
    'ignore:Cannot cache compiled function "numba_funcified_fgraph"'
)
def test_solve_triangular(b_func, b_size, lower, trans, unit_diag, complex):
    if complex:
        # TODO: Complex raises ValueError: To change to a dtype of a different size, the last axis must be contiguous,
        #  why?
        pytest.skip("Complex inputs currently not supported to solve_triangular")

    complex_dtype = "complex64" if config.floatX.endswith("32") else "complex128"
    dtype = complex_dtype if complex else config.floatX

    A = pt.matrix("A", dtype=dtype)
    b = b_func("b", dtype=dtype)

    X = pt.linalg.solve_triangular(
        A, b, lower=lower, trans=trans, unit_diagonal=unit_diag
    )
    f = pytensor.function([A, b], X, mode="NUMBA")

    A_val = np.random.normal(size=(5, 5))
    b = np.random.normal(size=b_size)

    if complex:
        A_val = A_val + np.random.normal(size=(5, 5)) * 1j
        b = b + np.random.normal(size=b_size) * 1j
    A_sym = A_val @ A_val.conj().T

    A_tri = np.linalg.cholesky(A_sym).astype(dtype)
    if unit_diag:
        adj_mat = np.ones((5, 5))
        adj_mat[np.diag_indices(5)] = 1 / np.diagonal(A_tri)
        A_tri = A_tri * adj_mat

    A_tri = A_tri.astype(dtype)
    b = b.astype(dtype)

    if not lower:
        A_tri = A_tri.T

    X_np = f(A_tri, b)
    np.testing.assert_allclose(
        transpose_func(A_tri, trans) @ X_np, b, atol=ATOL, rtol=RTOL
    )


@pytest.mark.parametrize("value", [np.nan, np.inf])
@pytest.mark.filterwarnings(
    'ignore:Cannot cache compiled function "numba_funcified_fgraph"'
)
def test_solve_triangular_raises_on_nan_inf(value):
    A = pt.matrix("A")
    b = pt.matrix("b")

    X = pt.linalg.solve_triangular(A, b, check_finite=True)
    f = pytensor.function([A, b], X, mode="NUMBA")
    A_val = np.random.normal(size=(5, 5))
    A_sym = A_val @ A_val.conj().T

    A_tri = np.linalg.cholesky(A_sym).astype(config.floatX)
    b = np.full((5, 1), value)

    with pytest.raises(
        ValueError, match=re.escape("Non-numeric values (nan or inf) returned ")
    ):
        f(A_tri, b)


def test_block_diag():
    A = pt.matrix("A")
    B = pt.matrix("B")
    C = pt.matrix("C")
    D = pt.matrix("D")
    X = pt.linalg.block_diag(A, B, C, D)

    A_val = np.random.normal(size=(5, 5))
    B_val = np.random.normal(size=(3, 3))
    C_val = np.random.normal(size=(2, 2))
    D_val = np.random.normal(size=(4, 4))
    out_fg = pytensor.graph.FunctionGraph([A, B, C, D], [X])
    compare_numba_and_py(out_fg, [A_val, B_val, C_val, D_val])
