import esprima
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class BookOfBlaseballVisitor(esprima.NodeVisitor):
    def find_book_function_node(self, node):
        self._ancestors = []
        self._book_function_node = None

        self.visit(node)

        return self._book_function_node

    def visit_Object(self, node):
        is_new = len(self._ancestors) == 0 or node != self._ancestors[len(self._ancestors) - 1]
        if is_new:
            self._ancestors.append(node)
        yield super().visit_Object(node)
        if is_new:
            self._ancestors.pop()

    def visit_Literal(self, node):
        if node.value != 'The Book of Blaseball' or self._book_function_node is not None or len(self._ancestors) <= 1:
            self.generic_visit(node)
            return

        for i in reversed(range(len(self._ancestors) - 2)):
            if self._ancestors[i].type == 'FunctionDeclaration':
                self._book_function_node = self._ancestors[i]
                break

        self.generic_visit(node)


class BookParserVisitor(esprima.NodeVisitor):
    def __init__(self):
        super().__init__()
        self._text = ''

    def parse_book(self, node):
        self._text = ''

        self.visit(node)

        return self._text

    def visit_CallExpression(self, node):
        is_create_element = (
            node.callee.type == 'MemberExpression' and
            node.callee.property.type == 'Identifier' and
            node.callee.property.name == 'createElement'
        )
        if not is_create_element:
            self.generic_visit(node)
            return

        self.visit(node.callee)

        for i in range(len(node.arguments)):
            if i == 0 and node.arguments[0].type == 'Literal':  # HTML tag
                if node.arguments[0].value == 'div' and self._text != '':
                    self._text += '\n'
                continue

            is_literal = (
                node.arguments[i].type == 'Literal' and
                node.arguments[i].value is not None
            )
            has_str_property = (
                node.arguments[i].type == 'ObjectExpression' and
                len(node.arguments[i].properties) == 1 and
                node.arguments[i].properties[0].key.name == 'str'
            )
            has_class_name_property = (
                node.arguments[i].type == 'ObjectExpression' and
                len(node.arguments[i].properties) == 1 and
                node.arguments[i].properties[0].key.name == 'className'
            )

            if is_literal:
                self._text += node.arguments[i].value
            elif has_str_property:
                self._text += node.arguments[i].properties[0].value.value
            elif has_class_name_property:
                class_names = node.arguments[i].properties[0].value.value.split(' ')
                if 'TheBook-Bullet' in class_names:
                    self._text += '\n'
                elif 'TheBook-SubBullet' in class_names:
                    self._text += '  '

            self.visit(node.arguments[i])


async def request_text(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()


async def parse_book_from_javascript():
    response = await request_text("https://blaseball.com/")
    if not response:
        raise Exception("Could not connect to blaseball.com")

    soup = BeautifulSoup(response, 'html.parser')

    script_tags = soup.select('script[src^="/static/js/main\."]')
    if len(script_tags) == 0:
        raise Exception('Could not find the main JS file.')
    if len(script_tags) > 1:
        raise Exception('More than one main JS files found.')

    script_tag = script_tags[0]
    src = script_tag.attrs['src']

    js_url = urljoin('https://blaseball.com', src)
    js = await request_text(js_url)

    ast = esprima.parse(js)

    book_of_blaseball_visitor = BookOfBlaseballVisitor()
    book_function_node = book_of_blaseball_visitor.find_book_function_node(ast)

    if book_function_node is None:
        raise Exception('Could not find the FunctionDeclaration node for rendering the Book in the AST.')

    book_parser_visitor = BookParserVisitor()

    return book_parser_visitor.parse_book(book_function_node), js_url


# if __name__ == '__main__':
#     try:
#         book = await parse_book_from_javascript()
#         print(book)
#     except Exception as e:
#         print(e)