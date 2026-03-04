"""
Neo4j 知识图谱检查工具
运行方式：python check_neo4j.py

功能：
  1. 测试连接
  2. 查看节点统计（题目/标签/公司/岗位数量）
  3. 查看向量索引状态
  4. 浏览最新题目
  5. 按标签查询题目
  6. 查看所有标签 / 公司
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
os.environ["PYTHONUTF8"] = "1"


def c(text, color="green"):
    codes = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
             "blue": "\033[94m", "cyan": "\033[96m", "bold": "\033[1m", "end": "\033[0m"}
    return f"{codes.get(color,'')}{text}{codes['end']}"


def title(text):
    print(f"\n{c('─'*50, 'blue')}\n  {c(text, 'bold')}\n{c('─'*50, 'blue')}")


def get_driver():
    from backend.config.config import settings
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(settings.neo4j_uri,
                                   auth=(settings.neo4j_username, settings.neo4j_password),
                                   connection_timeout=5)
    return driver, settings.neo4j_database


def run_query(driver, db, query, params=None):
    with driver.session(database=db) as session:
        result = session.run(query, **(params or {}))
        return [record.data() for record in result]


# ─── 功能函数 ───────────────────────────────────────────────────

def check_connection():
    title("1. 连接测试")
    try:
        driver, db = get_driver()
        result = run_query(driver, db, "RETURN 1 AS ok")
        print(f"  {c('✅ Neo4j 连接成功！', 'green')}")
        print(f"  URI: ", end="")
        from backend.config.config import settings
        print(settings.neo4j_uri)
        driver.close()
        return True
    except Exception as e:
        print(f"  {c('❌ 连接失败：' + str(e)[:120], 'red')}")
        print(f"\n  {c('提示：', 'yellow')} 请先运行 docker compose up -d 启动 Neo4j")
        return False


def show_stats():
    title("2. 节点统计")
    try:
        driver, db = get_driver()
        queries = [
            ("题目 (Question)", "MATCH (n:Question) RETURN count(n) AS cnt"),
            ("标签 (Tag)",      "MATCH (n:Tag)      RETURN count(n) AS cnt"),
            ("公司 (Company)",  "MATCH (n:Company)  RETURN count(n) AS cnt"),
            ("岗位 (Position)", "MATCH (n:Position) RETURN count(n) AS cnt"),
            ("概念 (Concept)",  "MATCH (n:Concept)  RETURN count(n) AS cnt"),
        ]
        for label, q in queries:
            result = run_query(driver, db, q)
            cnt = result[0]["cnt"] if result else 0
            bar = "█" * min(cnt, 30) if cnt > 0 else "（空）"
            print(f"  {label:<20} {c(str(cnt), 'cyan'):>6}  {bar}")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def show_vector_index():
    title("3. 向量索引状态")
    try:
        driver, db = get_driver()
        result = run_query(driver, db,
            "SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties "
            "WHERE type = 'VECTOR' RETURN name, state, labelsOrTypes, properties")
        if not result:
            print(f"  {c('⚠️  未找到向量索引（题目入库后会自动创建）', 'yellow')}")
        else:
            for r in result:
                state_color = "green" if r["state"] == "ONLINE" else "yellow"
                print(f"  索引名: {r['name']}")
                print(f"  状态:   {c(r['state'], state_color)}")
                print(f"  节点:   {r['labelsOrTypes']}  属性: {r['properties']}")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def show_recent_questions(limit=5):
    title(f"4. 最新 {limit} 道题目")
    try:
        driver, db = get_driver()
        result = run_query(driver, db,
            "MATCH (q:Question) "
            "OPTIONAL MATCH (q)-[:HAS_TAG]->(t:Tag) "
            "RETURN q.id AS id, q.text AS text, q.difficulty AS difficulty, "
            "q.company AS company, collect(t.name) AS tags "
            "ORDER BY q.created_at DESC LIMIT $limit",
            {"limit": limit})
        if not result:
            print("  （暂无题目，先通过收录面经入库）")
        for i, r in enumerate(result, 1):
            print(f"\n  [{i}] {c(r['text'][:70], 'bold')}...")
            print(f"      难度: {r.get('difficulty','-')}  公司: {r.get('company','-')}  "
                  f"标签: {r.get('tags',[])[:3]}")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def show_all_tags():
    title("5. 所有标签")
    try:
        driver, db = get_driver()
        result = run_query(driver, db,
            "MATCH (t:Tag)<-[:HAS_TAG]-(q:Question) "
            "RETURN t.name AS tag, count(q) AS cnt "
            "ORDER BY cnt DESC LIMIT 30")
        if not result:
            print("  （暂无标签）")
        else:
            for r in result:
                bar = "▪" * min(r["cnt"], 20)
                print(f"  {r['tag']:<20} {r['cnt']:>4} 题  {bar}")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def show_all_companies():
    title("6. 所有公司")
    try:
        driver, db = get_driver()
        result = run_query(driver, db,
            "MATCH (c:Company)<-[:FROM_COMPANY]-(q:Question) "
            "RETURN c.name AS company, count(q) AS cnt "
            "ORDER BY cnt DESC LIMIT 20")
        if not result:
            print("  （暂无公司数据）")
        else:
            for r in result:
                print(f"  {r['company']:<20} {r['cnt']:>4} 题")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def search_by_tag():
    tag = input("  输入标签（如 Redis）: ").strip()
    if not tag:
        return
    title(f"按标签 [{tag}] 查询")
    try:
        driver, db = get_driver()
        result = run_query(driver, db,
            "MATCH (t:Tag {name: $tag})<-[:HAS_TAG]-(q:Question) "
            "RETURN q.id AS id, q.text AS text, q.difficulty AS difficulty, q.company AS company "
            "ORDER BY rand() LIMIT 5",
            {"tag": tag})
        if not result:
            print(f"  未找到标签 [{tag}] 的题目")
        for i, r in enumerate(result, 1):
            print(f"\n  [{i}] {c(r['text'][:70], 'bold')}...")
            print(f"      难度: {r.get('difficulty','-')}  公司: {r.get('company','-')}")
        driver.close()
    except Exception as e:
        print(f"  {c('查询失败：' + str(e)[:100], 'red')}")


def create_vector_index():
    title("创建向量索引（1024维 cosine）")
    try:
        driver, db = get_driver()
        with driver.session(database=db) as session:
            session.run("""
                CREATE VECTOR INDEX question_embeddings IF NOT EXISTS
                FOR (n:Question) ON (n.embedding)
                OPTIONS {indexConfig: {
                  `vector.dimensions`: 1024,
                  `vector.similarity_function`: 'cosine'
                }}
            """)
        print(f"  {c('✅ 向量索引创建/确认完成', 'green')}")
        driver.close()
    except Exception as e:
        print(f"  {c('创建失败：' + str(e)[:100], 'red')}")


# ─── 主菜单 ────────────────────────────────────────────────────

MENU = [
    ("1", "连接测试", check_connection),
    ("2", "节点统计（题目/标签/公司数量）", show_stats),
    ("3", "向量索引状态", show_vector_index),
    ("4", "最新题目（5条）", show_recent_questions),
    ("5", "所有标签排行", show_all_tags),
    ("6", "所有公司排行", show_all_companies),
    ("7", "按标签搜索题目", search_by_tag),
    ("8", "手动创建向量索引", create_vector_index),
    ("a", "运行全部检查", None),
    ("q", "退出", None),
]


def main():
    print(c("""
╔═══════════════════════════════════════════╗
║     Neo4j 知识图谱检查工具  check_neo4j.py ║
╚═══════════════════════════════════════════╝""", "cyan"))

    while True:
        print(f"\n{c('请选择操作：', 'bold')}")
        for key, label, _ in MENU:
            print(f"  {c(key, 'cyan')}. {label}")

        choice = input("\n输入编号: ").strip().lower()

        if choice == "q":
            break
        elif choice == "a":
            if check_connection():
                show_stats()
                show_vector_index()
                show_recent_questions()
                show_all_tags()
                show_all_companies()
        else:
            matched = [(fn,) for k, _, fn in MENU if k == choice and fn is not None]
            if not matched:
                print(f"  {c('无效选项', 'yellow')}")
                continue
            matched[0][0]()

        input(f"\n{c('按回车继续...', 'blue')}")


if __name__ == "__main__":
    main()
