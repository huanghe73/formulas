#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2016-2017 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

"""
It provides AstBuilder class.
"""

import collections
import schedula
import schedula.utils as sh_utl
from .errors import FormulaError
from .tokens.operator import Operator
from .tokens.function import Function
from .tokens.operand import Operand
from .formulas.operators import References, wrap_ranges_func
from .constants import NAME_REFERENCES
from schedula.utils.alg import get_unused_node_id


class AstBuilder(collections.deque):
    def __init__(self, *args, dsp=None, map=None, match=None, **kwargs):
        super(AstBuilder, self).__init__(*args, **kwargs)
        self.match = match
        self.dsp = dsp or schedula.Dispatcher()
        self.map = map or {}
        self.missing_operands = set()
        self.references = References()

    def append(self, token):
        if isinstance(token, (Operator, Function)):
            try:
                tokens = [self.pop() for _ in range(token.get_n_args)][::-1]
            except IndexError:
                raise FormulaError()
            token.update_input_tokens(*tokens)
            inputs = [self.get_node_id(i) for i in tokens]
            token.set_expr(*tokens)
            out, dmap = token.node_id, self.dsp.dmap
            if out not in self.dsp.nodes:
                self.dsp.add_function(
                    function_id=get_unused_node_id(dmap, token.name),
                    function=token.compile(),
                    inputs=inputs or None,
                    outputs=[out]
                )
            else:
                self.map[token] = n_id = get_unused_node_id(dmap, out, 'c%d>{}')
                self.dsp.add_function(None, sh_utl.bypass, [out], [n_id])
        elif isinstance(token, Operand):
            self.missing_operands.add(token)

        super(AstBuilder, self).append(token)

    def get_node_id(self, token):
        if token in self.map:
            return self.map[token]
        if isinstance(token, Operand):
            self.missing_operands.remove(token)
            token.set_expr()
            kw = {}
            if token.attr.get('is_reference', False):
                self.references.push(token)
            else:
                kw['default_value'] = token.compile()

            node_id = self.dsp.add_data(data_id=token.node_id, **kw)
        else:
            node_id = token.node_id
        self.map[token] = node_id
        return node_id

    def finish(self):
        for token in list(self.missing_operands):
            self.get_node_id(token)

        if self.references.tokens:
            self.dsp.add_function(
                function=self.references,
                inputs=[NAME_REFERENCES],
                outputs=list(map(self.map.get, self.references.tokens))
            )
        node_id = self.get_node_id(self[-1])
        attr = self.dsp.get_node(node_id, node_attr=None)[0]
        attr['filters'] = wrap_ranges_func(sh_utl.bypass),

    def compile(self, inputs=None):
        dsp = self.dsp
        for k, v in dsp.dispatch(inputs or {}).items():
            dsp.add_data(data_id=k, default_value=v)

        i, o, pred = [], self.get_node_id(self[-1]), dsp.dmap.pred
        for k, v in sorted(dsp.data_nodes.items()):
            if not (k in dsp.default_values or len(pred[k])):
                i.append(k)

        return sh_utl.SubDispatchPipe(dsp, '=%s' % o, i, [o], wildcard=False)
