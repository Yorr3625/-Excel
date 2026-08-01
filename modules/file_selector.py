import os

ORDERS_FOLDER = "orders"


def select_order_file():

    if not os.path.exists(ORDERS_FOLDER):

        os.makedirs(ORDERS_FOLDER)

    files = []

    for file in os.listdir(ORDERS_FOLDER):

        if file.endswith((".xlsx", ".xlsm")):

            files.append(file)

    if not files:

        print("В папке 'orders' нет файлов Excel")

        input(
            "Нажмите Enter для выхода..."
        )

        exit()

    print("\nДоступные заказы:\n")

    for i, file in enumerate(
        files,
        start=1
    ):

        print(f"{i}. {file}")

    while True:

        try:

            choice = int(
                input(
                    "\nВыберите номер файла: "
                )
            )

            if (
                1 <= choice
                <= len(files)
            ):

                selected = files[
                    choice - 1
                ]

                return os.path.join(
                    ORDERS_FOLDER,
                    selected
                )

        except ValueError:

            pass

        print(
            "Неверный выбор, попробуйте снова"
        )