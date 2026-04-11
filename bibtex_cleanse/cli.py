"""命令行入口——只负责参数解析，所有逻辑委托给 core 模块。"""

import argparse

from .core import add, multiply, greet, _VERSION


def main(argv: list[str] | None = None) -> None:
    """CLI 主函数。`pyproject.toml` 中的 [project.scripts] 指向这里。"""
    parser = argparse.ArgumentParser(
        prog="mycli",
        description="my_package 的命令行工具",
    )
    parser.add_argument("-v", "--version", action="version", version=_VERSION)

    sub = parser.add_subparsers(dest="command")

    # greet 子命令
    p_greet = sub.add_parser("greet", help="问候某人")
    p_greet.add_argument("name", nargs="?", default="World")

    # add 子命令
    p_add = sub.add_parser("add", help="两数相加")
    p_add.add_argument("a", type=float)
    p_add.add_argument("b", type=float)

    # mul 子命令
    p_mul = sub.add_parser("mul", help="两数相乘")
    p_mul.add_argument("a", type=float)
    p_mul.add_argument("b", type=float)

    args = parser.parse_args(argv)

    match args.command:
        case "greet":
            print(greet(args.name))
        case "add":
            print(f"{args.a} + {args.b} = {add(args.a, args.b)}")
        case "mul":
            print(f"{args.a} \u00d7 {args.b} = {multiply(args.a, args.b)}")
