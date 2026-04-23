#   1 查詢與篩選   WHERE、LIKE、ORDER BY、LIMIT
#   2 聚合統計     GROUP BY、COUNT、SUM、AVG、HAVING
#   3 多表關聯     INNER JOIN、LEFT JOIN
#   4 交易控制     BEGIN / COMMIT / ROLLBACK

import os
import mysql.connector
from flask import Flask, request, jsonify
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

# os.environ.get() 第二個參數是預設值，當環境變數不存在時使用
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "user":     os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "bookstore"),
}


def get_db():  
    return mysql.connector.connect(**DB_CONFIG)
# 記得！ 結束後 cursor.close() / db.close()

# 第一段：資料表初始化

#   使用 CREATE TABLE IF NOT EXISTS，確保重複啟動時不會報錯。
#   "外鍵" 可以讓資料庫自己確保參照的完整性：不能讓一本書指定在一個不存在的出版社 ID，也不能刪除一間出版社，如果它底下還有書的話。

def create_tables():
    db = get_db()
    cursor = db.cursor()

    # 第 1 張表：publishers（出版社）
    # 獨立資料，不依賴其他任何表，所以優先建立。
    # founded 使用年份
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS publishers (
            id           INT PRIMARY KEY AUTO_INCREMENT,
            name         VARCHAR(100) NOT NULL,
            country      VARCHAR(50),
            founded      YEAR
        )
    """)

    #  第 2 張表：books（書本）
    # 依賴 publishers（id），所以在 publishers 之後建立。
    # 10進制 DECIMAL(10, 2) 代表最多 10 位數字，小數點後 2 位，
    # stock INT DEFAULT 0：庫存預設為 0，在新增書本時可以不傳這個欄位。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id           INT PRIMARY KEY AUTO_INCREMENT,
            title        VARCHAR(200) NOT NULL,
            author       VARCHAR(100),
            genre        VARCHAR(50),
            price        DECIMAL(10, 2) NOT NULL,
            stock        INT DEFAULT 0,
            publisher_id INT,
            FOREIGN KEY (publisher_id) REFERENCES publishers(id)
        )
    """)

    #  第 3 張表：customers（顧客）
    # 獨立資料
    # email 加上 UNIQUE ：每個 email 在系統中只能存在一筆資料，防止同一個信箱重複註冊。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            name       VARCHAR(100) NOT NULL,
            email      VARCHAR(150) UNIQUE,
            city       VARCHAR(50),
            join_date  DATE
        )
    """)

    #  第 4 張表：orders（訂單）
    # order_date 使用 DEFAULT CURRENT_TIMESTAMP，下單時間由資料庫自動填入。
    # status 使用 ENUM 列舉型別，只允許三種固定值，避免存入不合法狀態。
    # total_amount 在建立訂單時動態計算並寫入，方便查詢時直接使用。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id           INT PRIMARY KEY AUTO_INCREMENT,
            customer_id  INT NOT NULL,
            order_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
            status       ENUM('pending', 'paid', 'cancelled') DEFAULT 'pending',
            total_amount DECIMAL(10, 2) DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)

    # 第 5 張表：order_items（訂單明細）
    # 一本書也可以出現在多筆訂單中。直接在 orders 或 books 裡
    # 沒辦法直接存放對方的 ID ，因此需要這張中間表來記錄每一筆配對。
    # unit_price另外儲存，因為書的定價可能日後調整，像是特價的情況，訂單必須永遠保存「當時」的金額。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id         INT PRIMARY KEY AUTO_INCREMENT,
            order_id   INT NOT NULL,
            book_id    INT NOT NULL,
            quantity   INT NOT NULL DEFAULT 1,
            unit_price DECIMAL(10, 2) NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (book_id)  REFERENCES books(id)
        )
    """)

    db.commit()
    cursor.close()
    db.close()
    print("✅ 資料表與索引初始化完成")

# 第二段：範例資料插入

#   建立初始測試資料
#   先查詢 publishers 的資料有多少筆，若大於 0 代表已經插入過，直接 return 跳出函式，確保此段只會執行一次
#
#   executemany() 與 execute() 的差別：
#   execute()     ： 執行單一一條 SQL
#   executemany() ： 傳入資料列表，批次執行相同的 SQL，效率較高

def insert_sample_data():
    db = get_db()
    cursor = db.cursor()

    # 已有資料則跳過，避免重複插入
    cursor.execute("SELECT COUNT(*) FROM publishers")
    if cursor.fetchone()[0] > 0:
        cursor.close()
        db.close()
        return

    cursor.executemany(
        "INSERT INTO publishers (name, country, founded) VALUES (%s, %s, %s)",
        [
            ("天下文化",   "Taiwan", 1982),
            ("究竟出版",   "Taiwan", 2000),
            ("方智出版",   "Taiwan", 1988),
            ("Harper Design",   "USA", 2014),
        ]
    )

    cursor.executemany(
        "INSERT INTO books (title, author, genre, price, stock, publisher_id) VALUES (%s,%s,%s,%s,%s,%s)",
        [
            ("第六次大滅絕：不自然的歷史", "伊麗莎白‧寇伯特","歷史",  450, 30, 1),
            ("人類大歷史：知識漫畫1——人類誕生","哈拉瑞, 范德穆倫","歷史",  700, 25, 1),
            ("象與騎象人：全球百大思想家的正向心理學經典","強納森．海德","心理",  390, 15, 2),
            ("被討厭的勇氣：自我啟發之父「阿德勒」的教導","岸見一郎","心理",  300, 40, 2),
            ("原子習慣", "詹姆斯‧克利爾","心理",  330, 35, 3),
            ("臣服實驗：從隱居者到上市公司執行長，放手讓生命掌舵的旅程", "麥克‧辛格","人文",  320, 20, 3), 
            ("I Used to Have a Plan: But Life Had Other Ideas","Alessandra Olanow","心理",  665, 30, 4),            
        ]
    )

    cursor.executemany(
        "INSERT INTO customers (name, email, city, join_date) VALUES (%s,%s,%s,%s)",
        [
            ("陳怡君", "yijun@email.com",  "台北", "2023-01-15"),
            ("林俊宏", "junhong@email.com","高雄", "2023-03-22"),
            ("王雅婷", "yating@email.com", "台中", "2023-06-10"),
            ("張志偉", "zhiwei@email.com", "台南", "2024-01-05"),
        ]
    )

    db.commit()
    cursor.close()
    db.close()
    print("✅ 範例資料插入完成")

# 第三段：查詢與篩選 
#
#   模糊搜尋，萬用字元 %，可以匹配任意數量的字元
#
#   使用條件(conditions)和參數(params)做列表搭配使用：
#   conditions 收集每個 WHERE 條件的 SQL 片段（ %s ）
#   params     收集對應的實際值
#
#   最後用 " AND ".join(conditions) 拼接成完整的 WHERE 子句

@app.route("/books", methods=["GET"])
def get_books():
    """
    書本列表查詢，支援多種篩選與排序條件。

    可用查詢參數：
      genre     ： 篩選分類
      keyword   ： 可以搜尋書名或作者
      max_price ： 篩選售價的上限
      sort      ： 排序欄位（id / price / title / stock），預設 id
      limit     ： 回傳筆數上限，預設 20

    """
    genre     = request.args.get("genre")
    keyword   = request.args.get("keyword")
    max_price = request.args.get("max_price", type=float)
    sort      = request.args.get("sort", "id")
    limit     = request.args.get("limit",10, type=int)

    # 加入白名單，確保只能照著我給的條件搜尋，也是一個安全機制
    Whitelist_sort = {"id", "price", "title", "stock"}
    if sort not in Whitelist_sort:
        sort = "id"

    conditions = []
    params     = []

#這邊用truthy 判斷
    if genre:
        conditions.append("genre = %s")
        params.append(genre)

    if keyword:
        # 同時搜尋書名與作者，兩者之間用 OR，必須整體用括號包起來，確保與其他 AND 條件串起來的優先順序是對的

        conditions.append("(title LIKE %s OR author LIKE %s)")
        params += [f"%{keyword}%", f"%{keyword}%"]  #要加兩次，對應 title 和 author 各一個 %s

    if max_price:
        conditions.append("price <= %s")
        params.append(max_price)


    # 有條件才加 WHERE，否則查全表
    if conditions:
        where = "WHERE " + " AND ".join(conditions)
    else:
        where = ""
    #簡寫： where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT id, title, author, genre, price, stock FROM books
        {where}    
        ORDER  BY {sort}        
        LIMIT  %s
    """
    params.append(limit)

    db = get_db()
    cursor = db.cursor(dictionary=True)  # dictionary=True：結果以字典型別回傳，方便轉 JSON 所以 欄位名稱會更清楚。
    cursor.execute(sql, params)
    result = cursor.fetchall() #無資料則跳過
    cursor.close()
    db.close()

    return jsonify(result)


@app.route("/customers", methods=["GET"])
def get_customers():
    """

    可用查詢參數：
      city → 依城市篩選

    """
    city = request.args.get("city")

    conditions = []
    params     = []

    if city:
        conditions.append("city = %s")
        params.append(city)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM customers {where} ORDER BY join_date DESC",params)
    result = cursor.fetchall() #無資料則跳過
    cursor.close()
    db.close()

    return jsonify(result)


# 第四段：統計 
#
#   聚合（Aggregation）是將多筆資料「壓縮」成一個摘要數字的技術
#
#   GROUP BY：將資料依指定欄位分組，每組套用一次聚合函式。GROUP BY僅僅只是分組，數字還沒合併
#
#   HAVING：對聚合後的結果再次篩選
#     WHERE 作用於「原始資料列」，在 GROUP BY 之前執行
#     HAVING 作用於「分組後的結果」，在 GROUP BY 之後執行
#
#   COALESCE(值, 預設值)：若值為 NULL 則回傳預設值(0)

@app.route("/stats/books-by-genre", methods=["GET"])
def stats_books_by_genre():
    """
    依分類統計書本數量與價格資訊。

    可用查詢參數：
      min_count  只顯示書本數量達到門檻的屬性分類

    """
    min_count = request.args.get("min_count", 1, type=int)

    sql = """
        SELECT   genre,
                 COUNT(*)     AS book_count,
                 AVG(price)   AS avg_price,
                 SUM(stock)   AS total_stock,
                 MIN(price)   AS min_price,
                 MAX(price)   AS max_price
        FROM     books
        GROUP BY genre
        HAVING   COUNT(*) >= %s
        ORDER BY book_count DESC
    """
    # HAVING 在 GROUP BY 之後執行，因此可以對 COUNT(*) 的結果設條件

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, (min_count,))
    result = cursor.fetchall()
    cursor.close()
    db.close()

    # MySQL 的 DECIMAL 和 AVG 計算結果， Python 會收到Decimal 的型別， 要轉成 float 才能被 jsonify() 正確序列化
    for row in result:
        for i, j in row.items():
            if hasattr(j, "__float__"):
                row[i] = float(j)
    #result 的結果會是

    return jsonify(result)


@app.route("/stats/customer-spending", methods=["GET"])
def stats_customer_spending():
    """
    統計每位顧客的累計消費金額與訂單次數。

    可用查詢參數：
      min_amount  只顯示累計消費達到此金額的顧客

    """
    min_amount = request.args.get("min_amount", 0, type=float)

    sql = """
        SELECT   c.id,
                 c.name,
                 COUNT(o.id)              AS order_count,
                 COALESCE(SUM(o.total_amount), 0) AS total_spent

        FROM customers c
        LEFT JOIN orders o
               ON c.id = o.customer_id
              AND o.status = 'paid'

        GROUP BY c.id, c.name
        HAVING   COALESCE(SUM(o.total_amount), 0) >= %s
        ORDER BY total_spent DESC
    """
    #   使用 LEFT JOIN 顯示左表所有紀錄，確保沒有訂單的顧客也會出現在結果中。不過 o.id 等欄位為 NULL
    #   SUM 會計為 NULL（再用 COALESCE 轉成 0）
    #
    #   JOIN 只解決沒訂單的顧客不消失這個問題，右表的條件要加上 AND 
    #   AND o.status = 'paid'：只將「已付款」的訂單納入計算，取消或待付款的訂單不算消費金額

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, (min_amount,))
    result = cursor.fetchall()
    cursor.close()
    db.close()

    for row in result:
        for i, j in row.items():
            if hasattr(j, "__float__"):
                row[i] = float(j) if j is not None else 0.0

    return jsonify(result)


# 第五段：多表關聯

#   JOIN 在一條 SQL 中同時查詢多張資料表的欄位，透過共同欄位將不同表的資料列對齊合併
#   連續 JOIN 多次，每次都是在前一次的結果基礎上再合併
#
#   INNER JOIN（或直接寫 JOIN）：
#     只回傳兩張表都有對應資料的列
#
#   LEFT JOIN：
#     以左側資料表為主，即使右側沒有對應資料也會保留左側的列，右側欄位填 NULL。

@app.route("/orders/<int:order_id>/detail", methods=["GET"])
def get_order_detail(order_id):
    """
    查詢訂單的完整詳情，需要串聯 5 張資料表：
    orders + customers + order_items + books + publishers

    """

    sql = """
        SELECT
            o.id              AS order_id,
            o.order_date,
            o.status,
            o.total_amount,

            c.name            AS customer_name,
            c.email,

            b.title           AS book_title,
            b.author,
            b.genre,

            oi.quantity,
            oi.unit_price,

            p.name            AS publisher_name,
            p.country         AS publisher_country

        FROM        orders      o
        JOIN        customers   c   ON o.customer_id  = c.id
        JOIN        order_items oi  ON oi.order_id    = o.id
        JOIN        books       b   ON oi.book_id     = b.id
        JOIN        publishers  p   ON b.publisher_id = p.id

        WHERE  o.id = %s
        ORDER  BY oi.id
    """

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, (order_id,))
    rows = cursor.fetchall()
    cursor.close()
    db.close()

    if not rows:
        return jsonify({"msg": "找不到此訂單"}), 404

    # 將 SQL 結果拆分為「訂單」與「明細, SQL 每一列都會重複包含訂單與顧客資訊，只需要取一次值就好
    #訂單則需要每一列都列出來
    order = {
        "order_id":      rows[0]["order_id"],
        "order_date":    str(rows[0]["order_date"]),
        "status":        rows[0]["status"],
        "total_amount":  float(rows[0]["total_amount"]),
        "customer_name": rows[0]["customer_name"],
        "email":         rows[0]["email"]
    }
    items = [
        {
            "book_title":        r["book_title"],
            "author":            r["author"],
            "genre":             r["genre"],
            "publisher":         r["publisher_name"],
            "publisher_country": r["publisher_country"],
            "quantity":          r["quantity"],
            "unit_price":        float(r["unit_price"]),
        }
        for r in rows
    ]
    return jsonify({"order": order, "items": items})


@app.route("/books/with-publisher", methods=["GET"])
def books_with_publisher():
    """
    查詢書本列表，同時帶出所屬出版社資訊。

    """
    country = request.args.get("country")
    params  = []
    where   = ""

    if country:
        where  = "WHERE p.country = %s"
        params = [country]

    sql = f"""
        SELECT
            b.id, b.title, b.author, b.genre, b.price, b.stock,
            p.name         AS publisher_name,
            p.country      AS publisher_country,
            p.founded

        FROM  books b
        JOIN publishers p ON b.publisher_id = p.id
        {where}
        ORDER BY b.title
    """

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, params)
    result = cursor.fetchall()
    cursor.close()
    db.close()

    for row in result:
        if row.get("price") is not None: 
            row["price"] = float(row["price"])

    return jsonify(result)


# 第六段：交易控制 API

#   交易要就全部成功，不然就全部失敗，要避免程式在中間崩潰，資料庫可能處於不一致的狀態
#
#   FOR UPDATE 在讀取資料時，資料會被鎖住，避免同時有兩個交易讀取相同庫存，導致各自扣減庫存，造成超賣的情況。

@app.route("/orders", methods=["POST"])
def create_order():
    """
    建立訂單,同時處理：庫存扣減、金額計算、訂單建立，三者要同時在交易中達成。
    1. 開始交易
    2. 逐一確認每本書的庫存是否足夠（FOR UPDATE 鎖定）
    3. 逐一扣減庫存
    4. 計算總金額
    5. 建立訂單標頭（orders）
    6. 批次插入訂單明細（order_items）
    7. 全部成功COMMIT，任一步驟失敗則 ROLLBACK（所有操作撤回）

        """
    data        = request.json
    customer_id = data.get("customer_id")
    items       = data.get("items", [])

    if not customer_id or not items:
        return jsonify({"msg": "請提供 customer_id 與 items"}), 400

    db     = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        #交易開始 start_transaction 把接下來的所有操作要綁在一起
        db.start_transaction()

        total_amount = 0
        item_rows    = []

        for item in items:
            book_id  = item["book_id"]
            quantity = item["quantity"]

            # FOR UPDATE：讀取書本資料並鎖定，防止其他交易同時修改同一本書的庫存
            cursor.execute(
                "SELECT id, title, price, stock FROM books WHERE id = %s FOR UPDATE",
                (book_id,)
                )
            book = cursor.fetchone()

            #發生錯誤時用raise ValueError直接跳出try 
            if not book:
                raise ValueError(f"book_id={book_id} 不存在")

            if book["stock"] < quantity:
                raise ValueError(
                    f"《{book['title']}》庫存不足"
                    f"（現有：{book['stock']} 本，需求：{quantity} 本）"
                )

            # 庫存足夠，執行扣減
            cursor.execute(
                "UPDATE books SET stock = stock - %s WHERE id = %s",
                (quantity, book_id)
            )

            unit_price    = float(book["price"])
            total_amount += unit_price * quantity
            
            #先暫存每本書的明細，之後再一次寫入
            item_rows.append((book_id, quantity, unit_price))
        
        #for迴圈到這
        
        print(item_rows)
        # 開始建立訂單（狀態直接設為 paid）
        cursor.execute(
            "INSERT INTO orders (customer_id, total_amount, status) VALUES (%s, %s, 'pending')",
            (customer_id, total_amount)
        )
        order_id = cursor.lastrowid  # 取得剛才插入的訂單 ID

        # 批次插入訂單明細， executemany 效率更好  並且用 list comprehension簡化程式
        cursor.executemany(
            "INSERT INTO order_items (order_id, book_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
            [(order_id, b, q, p) for b, q, p in item_rows]
        )

        # 步驟完全正確後 COMMIT 
        db.commit()
        return jsonify({
            "msg":          "訂單建立成功",
            "order_id":     order_id,
            "total_amount": round(total_amount, 2),
            "item_count":   len(items),
        })

    except ValueError as e:
        #庫存不足、書不存在
        db.rollback()
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        # 資料庫或其他未預期錯誤
        db.rollback()
        return jsonify({"error": f"伺服器錯誤：{str(e)}"}), 500
        # 500 未知的錯誤
    
    finally:
        cursor.close()
        db.close()

@app.route("/orders/<int:order_id>/paid", methods=["PUT"])
def paid_order(order_id):

    """
    付款成功，更改訂單狀態

    """
    db = get_db()
    cursor = db.cursor(dictionary = True)

    try:
        db.start_transaction()

        # 確認訂單存在
        cursor.execute(
            "SELECT id, status FROM orders WHERE id = %s FOR UPDATE",
            (order_id,)
        )
        order = cursor.fetchone()

        if not order:
            raise ValueError("找不到此訂單")
        if order["status"] == "paid":
            raise ValueError("此訂單已成功付款")

        # 更新訂單狀態為付款成功
        cursor.execute(
        "UPDATE orders SET status = 'paid' WHERE id = %s",
        (order_id,)
        )

        db.commit()
        return jsonify({"cancel": f"訂單 {order_id} 號付款成功"})
    
    except ValueError as e:
        db.rollback()
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        db.rollback()
        return jsonify({"error": f"伺服器錯誤：{str(e)}"}), 500

    finally:
        cursor.close()
        db.close()


@app.route("/orders/<int:order_id>/cancel", methods=["PUT"])
def cancel_order(order_id):
    """
    取消訂單，同時將庫存歸還
    庫存回補與狀態變更必須同時成功，因此同樣放在交易中。

    """
    db     = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        db.start_transaction()

        # 確認訂單存在
        cursor.execute(
            "SELECT id, status FROM orders WHERE id = %s FOR UPDATE",
            (order_id,)
        )
        order = cursor.fetchone()

        if not order:
            raise ValueError("找不到此訂單")
        if order["status"] == "cancelled":
            raise ValueError("此訂單已經是取消狀態")

        # 查詢此訂單的所有書本明細，並逐一歸還庫存
        cursor.execute(
            "SELECT book_id, quantity FROM order_items WHERE order_id = %s",
            (order_id,)
        )
        items = cursor.fetchall()

        for item in items:
            cursor.execute(
                "UPDATE books SET stock = stock + %s WHERE id = %s",
                (item["quantity"], item["book_id"])
            )

        # 更新訂單狀態為已取消
        cursor.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = %s",
            (order_id,)
        )

        db.commit()
        return jsonify({"cancel": f"訂單 {order_id} 號取消成功"})

    except ValueError as e:
        db.rollback()
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        db.rollback()
        return jsonify({"error": f"伺服器錯誤：{str(e)}"}), 500

    finally:
        cursor.close()
        db.close()

# 第七段：基本 CRUD（新增資料用）

#   提供各資料表的新增與查詢端點。

@app.route("/publishers", methods=["GET"])
def get_publishers():
    """
    查詢出版社，依名稱排序。
    
    """
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM publishers ORDER BY name")
    result = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(result)

@app.route("/publishers", methods=["POST"])
def create_publisher():
    """
    新增出版社。

    """
    data = request.json
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM publishers WHERE name = %s AND country =%s", (data["name"],data.get("country")))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return jsonify({"msg": "已擁有此出版社資料"}), 409 
    # 404是找不到資料 409是以擁有資料

    cursor.execute(
        "INSERT INTO publishers (name, country, founded) VALUES (%s, %s, %s)",
        (data["name"], data.get("country"), data.get("founded"))
    )
    db.commit()
    new_id = cursor.lastrowid
    cursor.close()
    db.close()
    return jsonify({"msg": "出版社新增成功", "id": new_id})

@app.route("/customers", methods=["POST"])
def create_customer():
    """
    新增顧客。

    """
    data = request.json
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM customers WHERE name = %s AND email =%s", (data["name"],data["email"]))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return jsonify({"msg": "已擁有此顧客資料"}), 409
        
    cursor.execute(
        "INSERT INTO customers (name, email, city, join_date) VALUES (%s,%s,%s,%s)",
        (data["name"], data["email"], data.get("city"),
         data.get("join_date"))
    )
    db.commit()
    new_id = cursor.lastrowid
    cursor.close()
    db.close()
    return jsonify({"msg": "顧客新增成功", "id": new_id})

@app.route("/books", methods=["POST"])
def create_book():
    """
    新增書本。

    """
    data = request.json
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM books WHERE title = %s AND author =%s", (data["title"],data["author"]))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return jsonify({"msg": "已擁有此書"}), 409
    
    cursor.execute(
        "INSERT INTO books (title, author, genre, price, stock, publisher_id) VALUES (%s,%s,%s,%s,%s,%s)",
        (data["title"], data.get("author"), data.get("genre"),
         data["price"], data.get("stock", 0), data.get("publisher_id"))
    )
    db.commit()
    new_id = cursor.lastrowid
    cursor.close()
    db.close()
    return jsonify({"msg": "書本新增成功", "id": new_id})

#   啟動初始化
#   create_tables() 和 insert_sample_data() 放在模組最外層，只要 Flask import 這個檔案就會執行，不需要等待請求進來。
#
#   if __name__ == "__main__": 確保只有直接執行此檔案時才會啟動 Flask ，如果是透過 import 載入就不會誤啟動。
#   debug=True 讓程式碼修改後自動重啟伺服器，方便開發使用。

create_tables()
insert_sample_data()

if __name__ == "__main__":
    app.run(debug=True)
