import numpy as np

import pytensor.tensor as pt
from pytensor.compile.debugmode import _lessbroken_deepcopy
from pytensor.configdefaults import config
from pytensor.graph.basic import Apply, Constant, Variable
from pytensor.graph.op import Op
from pytensor.link.c.op import COp
from pytensor.tensor.type import scalar
from pytensor.tensor.type_other import SliceType
from pytensor.tensor.variable import TensorVariable
from pytensor.typed_list.type import TypedListType


class _typed_list_py_operators:
    def __getitem__(self, index):
        return getitem(self, index)

    def __len__(self):
        return length(self)

    def append(self, toAppend):
        return append(self, toAppend)

    def extend(self, toAppend):
        return extend(self, toAppend)

    def insert(self, index, toInsert):
        return insert(self, index, toInsert)

    def remove(self, toRemove):
        return remove(self, toRemove)

    def reverse(self):
        return reverse(self)

    def count(self, elem):
        return count(self, elem)

    # name "index" is already used by an attribute
    def ind(self, elem):
        return index_(self, elem)

    ttype = property(lambda self: self.type.ttype)
    dtype = property(lambda self: self.type.ttype.dtype)
    ndim = property(lambda self: self.type.ttype.ndim + 1)


class TypedListVariable(_typed_list_py_operators, Variable):
    """
    Subclass to add the typed list operators to the basic `Variable` class.

    """


TypedListType.variable_type = TypedListVariable


class TypedListConstant(_typed_list_py_operators, Constant):
    """
    Subclass to add the typed list operators to the basic `Variable` class.

    """


TypedListType.constant_type = TypedListConstant


class GetItem(COp):
    # See doc in instance of this Op or function after this class definition.
    view_map = {0: [0]}
    __props__ = ()

    def make_node(self, x, index):
        assert isinstance(x.type, TypedListType)
        if not isinstance(index, Variable):
            if isinstance(index, slice):
                index = Constant(SliceType(), index)
                return Apply(self, [x, index], [x.type()])
            else:
                index = pt.constant(index, ndim=0, dtype="int64")
                return Apply(self, [x, index], [x.ttype()])
        if isinstance(index.type, SliceType):
            return Apply(self, [x, index], [x.type()])
        elif isinstance(index, TensorVariable) and index.ndim == 0:
            assert index.dtype == "int64"
            return Apply(self, [x, index], [x.ttype()])
        else:
            raise TypeError("Expected scalar or slice as index.")

    def perform(self, node, inputs, outputs):
        (x, index) = inputs
        (out,) = outputs
        if not isinstance(index, slice):
            index = int(index)
        out[0] = x[index]

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        x_name, index = inp[0], inp[1]
        output_name = out[0]
        fail = sub["fail"]
        return (
            """
        %(output_name)s = (typeof %(output_name)s) PyList_GetItem( (PyObject*) %(x_name)s, *((npy_int64 *) PyArray_DATA(%(index)s)));
        if(%(output_name)s == NULL){
            %(fail)s
        }
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version(self):
        return (1,)


getitem = GetItem()
"""
Get specified slice of a typed list.

Parameters
----------
x
    Typed list.
index
    The index of the value to return from `x`.

"""


class Append(COp):
    # See doc in instance of this Op after the class definition.
    __props__ = ("inplace",)

    def __init__(self, inplace=False):
        self.inplace = inplace
        if self.inplace:
            self.destroy_map = {0: [0]}
            # TODO: make destroy_handler support having views and
            # destroyed version of multiple inputs.
            # self.view_map = {0: [1]}
        else:
            # TODO: make destroy_handler support multiple view
            # self.view_map = {0: [0, 1]}
            self.view_map = {0: [0]}

    def make_node(self, x, toAppend):
        assert isinstance(x.type, TypedListType)
        assert x.ttype == toAppend.type, (x.ttype, toAppend.type)
        return Apply(self, [x, toAppend], [x.type()])

    def perform(self, node, inputs, outputs):
        (x, toAppend) = inputs
        (out,) = outputs
        if not self.inplace:
            out[0] = list(x)
        else:
            out[0] = x
        # need to copy toAppend due to destroy_handler limitation
        toAppend = _lessbroken_deepcopy(toAppend)
        out[0].append(toAppend)

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        raise NotImplementedError("DISABLED AS WE NEED TO UPDATE IT TO COPY toAppend()")
        x_name, toAppend = inp[0], inp[1]
        output_name = out[0]
        fail = sub["fail"]
        if not self.inplace:
            init = (
                """
            %(output_name)s = (PyListObject*) PyList_GetSlice((PyObject*) %(x_name)s, 0, PyList_GET_SIZE((PyObject*) %(x_name)s)) ;
            """
                % locals()
            )
        else:
            init = f"""
            {output_name} =  {x_name};
            """
        return (
            init
            + """
        if(%(output_name)s==NULL){
                %(fail)s
        };
        if(PyList_Append( (PyObject*) %(output_name)s,(PyObject*) %(toAppend)s)){
            %(fail)s
        };
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version(self):
        return (1,)


append = Append()
"""
Append an element at the end of another list.

Parameters
----------
x
    The base typed list.
y
    The element to append to `x`.

"""


class Extend(COp):
    # See doc in instance of this Op after the class definition.
    __props__ = ("inplace",)

    def __init__(self, inplace=False):
        self.inplace = inplace
        if self.inplace:
            self.destroy_map = {0: [0]}
            # TODO: make destroy_handler support having views and
            # destroyed version of multiple inputs.
            # self.view_map = {0: [1]}
        else:
            # TODO: make destroy_handler support multiple view
            # self.view_map = {0: [0, 1]}
            self.view_map = {0: [0]}

    def make_node(self, x, toAppend):
        assert isinstance(x.type, TypedListType)
        assert toAppend.type.is_super(x.type)
        return Apply(self, [x, toAppend], [x.type()])

    def perform(self, node, inputs, outputs):
        (x, toAppend) = inputs
        (out,) = outputs
        if not self.inplace:
            out[0] = list(x)
        else:
            out[0] = x
        # need to copy toAppend due to destroy_handler limitation
        if toAppend:
            o = out[0]
            for i in toAppend:
                o.append(_lessbroken_deepcopy(i))

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        raise NotImplementedError("DISABLED AS WE NEED TO UPDATE IT TO COPY toAppend()")
        x_name, toAppend = inp[0], inp[1]
        output_name = out[0]
        fail = sub["fail"]
        if not self.inplace:
            init = (
                """
            %(output_name)s = (PyListObject*) PyList_GetSlice((PyObject*) %(x_name)s, 0, PyList_GET_SIZE((PyObject*) %(x_name)s)) ;
            """
                % locals()
            )
        else:
            init = f"""
            {output_name} =  {x_name};
            """
        return (
            init
            + """
        int i =0;
        int length = PyList_GET_SIZE((PyObject*) %(toAppend)s);
        if(%(output_name)s==NULL){
                %(fail)s
        };
        for(i; i < length; i++){
            if(PyList_Append( (PyObject*) %(output_name)s,(PyObject*) PyList_GetItem((PyObject*) %(toAppend)s,i))==-1){
                %(fail)s
            };
        }
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version_(self):
        return (1,)


extend = Extend()
"""
Append all elements of a list at the end of another list.

Parameters
----------
x
    The typed list to extend.
toAppend
    The typed list that will be added at the end of `x`.

"""


class Insert(COp):
    # See doc in instance of this Op after the class definition.
    __props__ = ("inplace",)

    def __init__(self, inplace=False):
        self.inplace = inplace
        if self.inplace:
            self.destroy_map = {0: [0]}
            # TODO: make destroy_handler support having views and
            # destroyed version of multiple inputs.
            # self.view_map = {0: [2]}
        else:
            # TODO: make destroy_handler support multiple view
            # self.view_map = {0: [0, 2]}
            self.view_map = {0: [0]}

    def make_node(self, x, index, toInsert):
        assert isinstance(x.type, TypedListType)
        assert x.ttype == toInsert.type
        if not isinstance(index, Variable):
            index = pt.constant(index, ndim=0, dtype="int64")
        else:
            assert index.dtype == "int64"
            assert isinstance(index, TensorVariable) and index.ndim == 0
        return Apply(self, [x, index, toInsert], [x.type()])

    def perform(self, node, inputs, outputs):
        (x, index, toInsert) = inputs
        (out,) = outputs
        if not self.inplace:
            out[0] = list(x)
        else:
            out[0] = x
        # need to copy toAppend due to destroy_handler limitation
        toInsert = _lessbroken_deepcopy(toInsert)
        out[0].insert(index, toInsert)

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        raise NotImplementedError("DISABLED AS WE NEED TO UPDATE IT TO COPY toAppend()")
        x_name, index, toInsert = inp[0], inp[1], inp[2]
        output_name = out[0]
        fail = sub["fail"]
        if not self.inplace:
            init = (
                """
            %(output_name)s = (PyListObject*) PyList_GetSlice((PyObject*) %(x_name)s, 0, PyList_GET_SIZE((PyObject*) %(x_name)s)) ;
            """
                % locals()
            )
        else:
            init = f"""
            {output_name} =  {x_name};
            """
        return (
            init
            + """
        if(%(output_name)s==NULL){
                %(fail)s
        };
        if(PyList_Insert((PyObject*) %(output_name)s, *((npy_int64 *) PyArray_DATA(%(index)s)), (PyObject*) %(toInsert)s)==-1){
            %(fail)s
        };
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version(self):
        return (1,)


insert = Insert()
"""
Insert an element at an index in a typed list.

Parameters
----------
x
    The typed list to modify.
index
    The index where to put the new element in `x`.
toInsert
    The new element to insert.

"""


class Remove(Op):
    # See doc in instance of this Op after the class definition.
    __props__ = ("inplace",)

    def __init__(self, inplace=False):
        self.inplace = inplace
        if self.inplace:
            self.destroy_map = {0: [0]}
        else:
            self.view_map = {0: [0]}

    def make_node(self, x, toRemove):
        assert isinstance(x.type, TypedListType)
        assert x.ttype == toRemove.type
        return Apply(self, [x, toRemove], [x.type()])

    def perform(self, node, inputs, outputs):
        (x, toRemove) = inputs
        (out,) = outputs
        if not self.inplace:
            out[0] = list(x)
        else:
            out[0] = x

        """
        Inelegant workaround for ValueError: The truth value of an
        array with more than one element is ambiguous. Use a.any() or a.all()
        being thrown when trying to remove a matrix from a matrices list.
        """
        for y in range(out[0].__len__()):
            if node.inputs[0].ttype.values_eq(out[0][y], toRemove):
                del out[0][y]
                break

    def __str__(self):
        return self.__class__.__name__


remove = Remove()
"""Remove an element from a typed list.

Parameters
----------
x
    The typed list to be changed.
toRemove
    An element to be removed from the typed list.
    We only remove the first instance.

Notes
-----
Python implementation of remove doesn't work when we want to remove an ndarray
from a list. This implementation works in that case.

"""


class Reverse(COp):
    # See doc in instance of this Op after the class definition.
    __props__ = ("inplace",)

    def __init__(self, inplace=False):
        self.inplace = inplace
        if self.inplace:
            self.destroy_map = {0: [0]}
        else:
            self.view_map = {0: [0]}

    def make_node(self, x):
        assert isinstance(x.type, TypedListType)
        return Apply(self, [x], [x.type()])

    def perform(self, node, inp, outputs):
        (out,) = outputs
        if not self.inplace:
            out[0] = list(inp[0])
        else:
            out[0] = inp[0]
        out[0].reverse()

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        x_name = inp[0]
        output_name = out[0]
        fail = sub["fail"]
        if not self.inplace:
            init = (
                """
            %(output_name)s = (PyListObject*) PyList_GetSlice((PyObject*) %(x_name)s, 0, PyList_GET_SIZE((PyObject*) %(x_name)s)) ;
            """
                % locals()
            )
        else:
            init = f"""
            {output_name} =  {x_name};
            """
        return (
            init
            + """
        if(%(output_name)s==NULL){
                %(fail)s
        };
        if(PyList_Reverse((PyObject*) %(output_name)s)==-1){
            %(fail)s
        };
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version(self):
        return (1,)


reverse = Reverse()
"""
Reverse the order of a typed list.

Parameters
----------
x
    The typed list to be reversed.

"""


class Index(Op):
    # See doc in instance of this Op after the class definition.
    __props__ = ()

    def make_node(self, x, elem):
        assert isinstance(x.type, TypedListType)
        assert x.ttype == elem.type
        return Apply(self, [x, elem], [scalar()])

    def perform(self, node, inputs, outputs):
        """
        Inelegant workaround for ValueError: The truth value of an
        array with more than one element is ambiguous. Use a.any() or a.all()
        being thrown when trying to remove a matrix from a matrices list
        """
        (x, elem) = inputs
        (out,) = outputs
        for y in range(len(x)):
            if node.inputs[0].ttype.values_eq(x[y], elem):
                out[0] = np.asarray(y, dtype=config.floatX)
                break

    def __str__(self):
        return self.__class__.__name__


index_ = Index()


class Count(Op):
    # See doc in instance of this Op after the class definition.
    __props__ = ()

    def make_node(self, x, elem):
        assert isinstance(x.type, TypedListType)
        assert x.ttype == elem.type
        return Apply(self, [x, elem], [scalar()])

    def perform(self, node, inputs, outputs):
        """
        Inelegant workaround for ValueError: The truth value of an
        array with more than one element is ambiguous. Use a.any() or a.all()
        being thrown when trying to remove a matrix from a matrices list
        """
        (x, elem) = inputs
        (out,) = outputs
        out[0] = 0
        for y in range(len(x)):
            if node.inputs[0].ttype.values_eq(x[y], elem):
                out[0] += 1
        out[0] = np.asarray(out[0], dtype=config.floatX)

    def __str__(self):
        return self.__class__.__name__


count = Count()
"""
Count the number of times an element is in the typed list.

Parameters
----------
x
    The typed list to look into.
elem
    The element we want to count in list.
    The elements are compared with equals.

Notes
-----
Python implementation of count doesn't work when we want to count an ndarray
from a list. This implementation works in that case.

"""


class Length(COp):
    # See doc in instance of this Op after the class definition.
    __props__ = ()

    def make_node(self, x):
        assert isinstance(x.type, TypedListType)
        return Apply(self, [x], [scalar(dtype="int64")])

    def perform(self, node, x, outputs):
        (out,) = outputs
        out[0] = np.asarray(len(x[0]), "int64")

    def __str__(self):
        return self.__class__.__name__

    def c_code(self, node, name, inp, out, sub):
        x_name = inp[0]
        output_name = out[0]
        fail = sub["fail"]
        return (
            """
        if(!%(output_name)s)
            %(output_name)s=(PyArrayObject*)PyArray_EMPTY(0, NULL, NPY_INT64, 0);
        ((npy_int64*)PyArray_DATA(%(output_name)s))[0]=PyList_Size((PyObject*)%(x_name)s);
        Py_INCREF(%(output_name)s);
        """
            % locals()
        )

    def c_code_cache_version(self):
        return (1,)


length = Length()
"""
Returns the size of a list.

Parameters
----------
x
    Typed list.

"""


class MakeList(Op):
    __props__ = ()

    def make_node(self, a):
        assert isinstance(a, (tuple, list))
        a2 = []
        for elem in a:
            if not isinstance(elem, Variable):
                elem = pt.as_tensor_variable(elem)
            a2.append(elem)
        if not all(a2[0].type.is_super(elem.type) for elem in a2):
            raise TypeError("MakeList need all input variable to be of the same type.")
        tl = TypedListType(a2[0].type)()

        return Apply(self, a2, [tl])

    def perform(self, node, inputs, outputs):
        (out,) = outputs
        # We need to make sure that we don't get a view on our inputs
        out[0] = [_lessbroken_deepcopy(inp) for inp in inputs]


make_list = MakeList()
"""
Build a Python list from those PyTensor variable.

Parameters
----------
a : tuple/list of PyTensor variable

Notes
-----
All PyTensor variables must have the same type.

"""
