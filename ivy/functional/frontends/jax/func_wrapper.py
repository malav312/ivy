# global
import functools
import inspect
from typing import Callable

# local
import ivy
import ivy.functional.frontends.jax as jax_frontend


def _is_jax_frontend_array(x):
    return isinstance(x, jax_frontend.DeviceArray)


def _from_jax_frontend_array_to_ivy_array(x):
    if isinstance(x, jax_frontend.DeviceArray):
        return x.data
    return x


def _from_ivy_array_to_jax_frontend_array(x, nested=False, include_derived=None):
    if nested:
        return ivy.nested_map(x, _from_ivy_array_to_jax_frontend_array, include_derived)
    elif isinstance(x, ivy.Array):
        return jax_frontend.DeviceArray(x)
    return x


def _from_ivy_array_to_jax_frontend_array_order_F(
    x, nested=False, include_derived=None
):
    if nested:
        return ivy.nested_map(
            x, _from_ivy_array_to_jax_frontend_array_order_F, include_derived
        )
    elif isinstance(x, ivy.Array):
        return jax_frontend.DeviceArray(x, f_contiguous=True)
    return x


def _native_to_ivy_array(x):
    if isinstance(x, ivy.NativeArray):
        return ivy.array(x)
    return x


def _to_ivy_array(x):
    return _from_jax_frontend_array_to_ivy_array(_native_to_ivy_array(x))


def _check_C_order(x):
    if isinstance(x, ivy.Array):
        return True
    elif isinstance(x, jax_frontend.DeviceArray):
        if x.f_contiguous:
            return False
        else:
            return True
    else:
        return None


def _set_order(args, order):
    ivy.assertions.check_elem_in_list(
        order,
        ["C", "F", "A", "K", None],
        message="order must be one of 'C', 'F', 'A', or 'K'",
    )
    if order in ["K", "A", None]:
        check_order = ivy.nested_map(
            args, _check_C_order, include_derived={tuple: True}
        )
        if all(v is None for v in check_order) or any(
            ivy.multi_index_nest(check_order, ivy.all_nested_indices(check_order))
        ):
            order = "C"
        else:
            order = "F"
    return order


def inputs_to_ivy_arrays(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def new_fn(*args, **kwargs):
        # check if kwargs contains an out argument, and if so, remove it
        has_out = False
        out = None
        if "out" in kwargs:
            out = kwargs["out"]
            del kwargs["out"]
            has_out = True
        # convert all arrays in the inputs to ivy.Array instances
        new_args = ivy.nested_map(args, _to_ivy_array, include_derived={tuple: True})
        new_kwargs = ivy.nested_map(
            kwargs, _to_ivy_array, include_derived={tuple: True}
        )
        # add the original out argument back to the keyword arguments
        if has_out:
            new_kwargs["out"] = out
        return fn(*new_args, **new_kwargs)

    return new_fn


def outputs_to_frontend_arrays(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def new_fn(*args, order="K", **kwargs):
        # call unmodified function
        if contains_order:
            if len(args) >= (order_pos + 1):
                order = args[order_pos]
                args = args[:-1]
            order = _set_order(args, order)
            print(order)
            ret = fn(*args, order=order, **kwargs)
        else:
            ret = fn(*args, **kwargs)
        # convert all arrays in the return to `jax_frontend.DeviceArray` instances
        if order == "F":
            return _from_ivy_array_to_jax_frontend_array_order_F(
                ret, nested=True, include_derived={tuple: True}
            )
        else:
            return _from_ivy_array_to_jax_frontend_array(
                ret, nested=True, include_derived={tuple: True}
            )

    if "order" in list(inspect.signature(fn).parameters.keys()):
        contains_order = True
        order_pos = list(inspect.signature(fn).parameters).index("order")
    else:
        contains_order = False
    return new_fn


def to_ivy_arrays_and_back(fn: Callable) -> Callable:
    return outputs_to_frontend_arrays(inputs_to_ivy_arrays(fn))
