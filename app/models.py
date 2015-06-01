from app import db, redis_c
import os
import redis
import json
import datetime
from sqlalchemy.sql import text

class WordAll(db.Model):
    word_id = db.Column(db.Integer, primary_key=True)
    word_string = db.Column(db.String(8), nullable=False, unique=True)
    reported = db.Column(db.SmallInteger)

    def __init__(self, word_string):
        self.word_string = word_string
        self.reported = 0


class WordSearch(db.Model):
    word_id = db.Column(db.Integer, db.ForeignKey('word_all.word_id', ondelete='CASCADE'), primary_key=True)
    word_parsed = db.Column(db.String(24), nullable=False)

    def __init__(self, word_id, word_parsed):
        self.word_id = word_id
        self.word_parsed = word_parsed

class CandidateWord(db.Model):
    word_id = db.Column(db.Integer, db.ForeignKey('word_all.word_id', ondelete='CASCADE'), primary_key=True)
    vote = db.Column(db.Integer)

    def __init(self, word_id):
        self.word_id = word_id
        self.vote = 0


class ReportLog(db.Model):
    report_id = db.Column(db.Integer, primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('word_all.word_id', ondelete='CASCADE'), nullable=False)
    report_type = db.Column(db.SmallInteger, db.ForeignKey('report_class.report_type'), nullable=False)
    report_detail = db.Column(db.String(80))

    def __init__(self, word_id, report_type, report_detail):
        self.word_id = word_id
        self.report_type = report_type
        self.report_detail = report_detail


class ReportClass(db.Model):
    report_type = db.Column(db.SmallInteger, primary_key=True)
    report_name = db.Column(db.String(24))


class WordRank(db.Model):
    word_id = db.Column(db.Integer, db.ForeignKey('word_search.word_id', ondelete='CASCADE'), primary_key=True)
    rank_good = db.Column(db.Integer)
    rank_bad = db.Column(db.Integer)
    viewed = db.Column(db.Integer)
    fresh_rate = db.Column(db.Integer)

    def __init__(self, word_id):
        self.word_id = word_id
        self.rank_good = 0
        self.rank_bad = 0
        self.viewed = 0
        self.fresh_rate = 0


class RankLog(db.Model):
    word_id = db.Column(db.Integer, db.ForeignKey('word_search.word_id', ondelete='CASCADE'), primary_key=True)
    elapsed_date = db.Column(db.Date, primary_key=True, nullable=False, autoincrement=False)
    rank_good = db.Column(db.Integer)
    rank_bad = db.Column(db.Integer)
    viewed = db.Column(db.Integer)

    def __init__(self, word_id):
        self.word_id = word_id
        self.elapsed_date = date.today().isoformat()
        self.rank_bad = 0
        self.rank_good = 0
        self.viewed = 0


RAWQUERY = {
    'word_upvote': [text('UPDATE word_rank SET rank_good = rank_good + 1 WHERE word_id = :word_id'),
                    text('UPDATE rank_log SET rank_good = rank_good + 1 WHERE word_id = :word_id and elapsed_date = '+date.today().isoformat() )],
    'word_downvote': [text('UPDATE word_rank SET rank_bad = rank_bad + 1 WHERE word_id = :word_id'),
                      text('UPDATE rank_log SET rank_bad = rank_bad + 1 WHERE word_id = :word_id and elapsed_date = '+date.today().isoformat() )],
    'word_view': [text('UPDATE word_rank SET viewed = viewed + 1 WHERE word_id = :word_id'),
                  text('UPDATE rank_log SET viewed = viewed + 1 WHERE word_id = :word_id and elapsed_date = '+ date.today().isoformat() )],
    'word_search': text('''
    SELECT word_id, word_string, rank_good, rank_bad, viewed, fresh_rate, reported
    FROM (word_search NATURAL JOIN word_all) NATURAL JOIN word_rank
    WHERE word_parsed REGEXP :word
    '''),
    'get_word_id': text('''
    SELECT word_id
    FROM word_all
    WHERE word_string = :word_str
    '''),
    'get_word_data': text('''
    SELECT * FROM word_rank WHERE word_id = :word_id
    '''),
    'get_candidate':text('''
    SELECT candidate_word.word_id, word_string, vote
    FROM candidate_word JOIN word_all ON candidate_word.word_id = word_all.word_id
    ORDER BY :column_name ASC
    LIMIT :page_num, :fetch_num
    '''),
    'get_candidate_count':text('''
    SELECT count(*)
    FROM candidate_word
    '''),
    'get_report':text('''
    SELECT report_name, word_string, report_detail, count(*) as report_count
    FROM report_log JOIN report_class ON report_log.report_type = report_class.report_type
    JOIN word_all ON report_log.word_id = word_all.word_id
    GROUP BY report_log.word_id
    ORDER BY :column_name ASC
    LIMIT :page_num, :fetch_num
    '''),
    'get_report_count':text('''
    SELECT count(*)
    FROM report_log
    '''),
    'word_candidate_upvote':text('UPDATE candidate_word SET vote = vote + 1 WHERE word_id = :word_id'),
    'word_candidate_downvote':text('UPDATE candidate_word SET vote = vote - 1 WHERE word_id = :word_id'),
    'word_candidate_move': text('DELETE FROM word_candidate WHERE word_id = :word_id'),
    'report': text('UPDATE word_all SET reported = reported + 1 WHERE word_id = :word_id'),
    'word_delete': text('DELETE FROM word_all WHERE word_id = :word_id'),
    'fresh_rate': text('''
    WITH fresh_raw(word_id, rate) as
    (
        SELECT word_id, (DATEDIFF(CURRENT_DATE(), elapsed_date)) * (viewed + 10 * (rank_good + rank_bad))
        FROM rank_log
    ), max_rate(val) as (SELECT max(rate) FROM fresh_raw)
    UPDATE word_rank SET fresh_rate =
    (
        SELECT 100 * fresh_raw.rate / max_rate.val
        FROM fresh_raw, max_rate
        WHERE word_rank.word_id = fresh_raw.word_id
    )
    '''),
    'elapse_time':# [text('UPDATE rank_log SET elapsed_date = elapsed_date + 1'),
                    text('DELETE FROM rank_log WHERE DATEDIFF(CURRENT_DATE(), elapsed_date) >= 30'),#],
    'get_search_json': text('''
		SELECT word_rank.word_id AS word_id, word_all.word_string AS word_string, rank_good, rank_bad, viewed, fresh_rate 
		FROM (word_all NATURAL JOIN word_rank) 
		WHERE (word_all.word_id IN (SELECT word_id FROM word_search AS search WHERE (search.word_parsed REGEXP :regex))) 
		ORDER BY (:column_name) 
		LIMIT (:start_index), (:counts_per_page)
		''')
}
JAMOTABLE = {
    'ㄱ': '0', 'ㄴ': '1', 'ㄷ': '2', 'ㄹ': '3', 'ㅁ': '4', 'ㅂ': '5', 'ㅅ': '6', 'ㅇ': '7', 'ㅈ': '8', 'ㅊ': '9',
    'ㅋ': 'a', 'ㅌ': 'b', 'ㅍ': 'c', 'ㅎ': 'd', 'ㄲ': 'e', 'ㅆ': 'f', 'ㅃ': 'g', 'ㄸ': 'h', 'ㅉ': 'i', 'ㄳ': 'j',
    'ㄵ': 'k', 'ㄶ': 'l', 'ㄺ': 'm', 'ㄻ': 'n', 'ㄼ': 'o', 'ㄽ': 'p', 'ㄾ': 'q', 'ㄿ': 'r', 'ㅀ': 's', 'ㅄ': 't',
    'ㅏ': 'A', 'ㅑ': 'B', 'ㅓ': 'C', 'ㅕ': 'D', 'ㅗ': 'E', 'ㅛ': 'F', 'ㅜ': 'G', 'ㅠ': 'H', 'ㅡ': 'I', 'ㅣ': 'J',
    'ㅐ': 'K', 'ㅒ': 'L', 'ㅔ': 'M', 'ㅖ': 'N', 'ㅘ': 'O', 'ㅙ': 'P', 'ㅚ': 'Q', 'ㅝ': 'R', 'ㅞ': 'S', 'ㅟ': 'T',
    'ㅢ': 'U', 'X': 'V'
}
JAMOPARSE = [
    [JAMOTABLE[x] for x in ["ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ",
                            "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ", 'X']],
    [JAMOTABLE[x] for x in ["ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ", "ㅙ",
                            "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ", 'X']],
    [JAMOTABLE[x] for x in ["X", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ",
                            "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]]
]

def parse_char(c):
    pos = ord(c) - 0xac00
    last = pos % 28
    middle = ((pos-last)//28) % 21
    first = (((pos-last)//28)-middle)//21
    return JAMOPARSE[0][first] + JAMOPARSE[1][middle] + JAMOPARSE[2][last]

def parse_string(s):
    ret_val = ''
    for c in s:
        ret_val += parse_char(c)
    return ret_val

def parse_jlist(lst):
    if '*' in lst:
        return '.'
    elif len(lst) == 1:
        return JAMOTABLE[lst[0]]
    ret_val = '['
    for c in [JAMOTABLE[x] for x in lst]:
        ret_val += c
    return ret_val + ']'

def parse_to_regex(jamo_tup):
    """
    :param jamo_tup:
        '성가대...' is in ['?', [['ㄱ','ㄴ'],['ㅏ'], ['X']], [['ㄷ'],['ㅐ','ㅏ'],['*']], '*']
    :return: regex string
    """
    if jamo_tup == ['*']:
        return '.*'
    ret_val = '^'
    for tup in jamo_tup:
        if tup == '?':
            ret_val += '...'
            continue
        elif tup == '*':
            ret_val += '*'
            continue
        (fst, mid, lst) = (tup[0], tup[1], tup[2])
        ret = parse_jlist(fst) + parse_jlist(mid) + parse_jlist(lst)
        ret_val += ret

    ret_val += '$'
    return ret_val

def get_search_json(word_regex, page_num, fetch_num, column_name):
		counts_per_page = fetch_num if (fetch_num != 0) else 15
		order_column_name = column_name if (column_name != "") else 'word_string'
		start_index = counts_per_page * (page_num - 1)
		result = db.session.execute(RAWQUERY['get_search_json'], regex=word_regex, start_index=start_index, column_name=order_column_name, counts_per_page=counts_per_page).fetchall()
		ret_val = {
			'word_count': len(result),
			'dict':result
		}
		return json.dumps(ret_val)

def word_insert(word):
    db.session.add(WordAll(word))
    db.session.commit()

def word_candidate_insert(word):
    w = WordAll(word)
    db.session.add(w)
    db.session.commit()
    db.session.add(CandidateWord(w.word_id))
    db.session.commit()
    redis_c.set('id_' + str(w.word_id), word)

def word_candidate_move(word_id):
    db.session.add(WordSearch(word_id, parse_string(get_word(str(word_id)))))
    db.session.commit()
    db.session.add(WordRank(word_id))
    db.session.commit()
    db.engine.execute(RAWQUERY['word_candidate_move'], word_id=word_id)

def word_candidate_upvote(word_id):
    db.engine.execute(RAWQUERY['word_candidate_upvote'], word_id=word_id)

def word_candidate_downvote(word_id):
    db.engine.execute(RAWQUERY['word_candidate_downvote'], word_id=word_id)

def word_search_insert(word):
    w = WordAll(word)
    db.session.add(w)
    db.session.commit()
    db.session.add(WordSearch(w.word_id, parse_string(word)))
    db.session.commit()
    db.session.add(WordRank(w.word_id))
    db.session.commit()
    redis_c.set('id_' + str(w.word_id), word)

def report(word_id, report_type, report_detail):
    db.session.add(ReportLog(word_id, report_type, report_detail))
    db.session.commit()
    db.engine.execute(RAWQUERY['report'], word_id=word_id)

def candidate_report(word_id, report_type, report_detail):
    report(word_id, report_type, report_detail)

def get_candidate_json(page_num, fetch_num, column_name):
    candidate_result = db.engine.execute(RAWQUERY['get_candidate'], column_name=column_name, page_num=page_num * fetch_num, fetch_num=fetch_num)
    count_result = db.engine.execute(RAWQUERY['get_candidate_count']).first()
    candidate_data = {
      'word_count': count_result[0],
      'candidates':[]
    }
    for row in candidate_result:
      data = {
        'word_id':row[0],
        'word_string':row[1],
        'vote':row[2]
      }
      candidate_data.append(row)

    return json.dumps(candidate_data)

def get_admin_json(page_num, fetch_num, recent):
    # recent : 0 -> 신고시간, 1 -> 신고 많이 받은 순서
    # 좀 모호한데....
    column_name = 'report_count'
    if recent == 0:
      column_name = 'report_id'

    admin_result = db.engine.execute(RAWQUERY['get_report'], column_name=column_name, page_num=page_num * fetch_num, fetch_num=fetch_num)
    count_result = db.engine.execute(RAWQUERY['get_report_count']).first()
    admin_data = {
      'report_count': count_result[0],
      'admins':[]
    }
    for row in admin_result:
      data = {
        'report_name':row[0],
        'word_string':row[1],
        'report_detail':row[2]
      }
      admin_data.append(row)

    return json.dumps(admin_data)

def word_report(word_id, report_type, report_detail):
    report(word_id, report_type, report_detail)

def word_delete(word_id):
    db.engine.execute(RAWQUERY['word_delete'], word_id=word_id)
    redis_c.delete('id_' + str(word_id))

def word_upvote(word_id):
    db.engine.execute(RAWQUERY['word_upvote'][0], word_id=word_id)
    db.engine.execute(RAWQUERY['word_upvote'][1], word_id=word_id)

def word_downvote(word_id):
    db.engine.execute(RAWQUERY['word_downvote'][0], word_id=word_id)
    db.engine.execute(RAWQUERY['word_downvote'][1], word_id=word_id)

def word_view(word_id):
    db.engine.execute(RAWQUERY['word_view'][0], word_id=word_id)
    db.engine.execute(RAWQUERY['word_view'][1], word_id=word_id)

def word_search(word_regex):
    result = db.engine.execute(RAWQUERY['word_search'], word=word_regex)
    for word in result.fetchmany(10):
        print(word)

def get_word(word_id_str):
    return redis_c.get('id_' + word_id_str).decode('utf-8')

def get_word_id(word_str):
    result = db.engine.execute(RAWQUERY['get_word_id'], word_str=word_str).first()
    if result is None:
      return -1
    else:
      return result[0]

def get_word_data(word_id):
    result = db.engine.execute(RAWQUERY['get_word_data'], word_id=word_id).first()
    word_data = {
        'word_id': word_id,
        'word_string': get_word(str(word_id)),
        'rank_good': result[1],
        'rank_bad': result[2],
        'viewed': result[3],
        'fresh_rate': result[4]
    }
    return word_data

def get_word_json(word_id, tag_count):
    word_data = get_word_data(word_id)
    tag = tag_fetch(word_id, tag_count)
    word_data['tag'] = tag
    return json.dumps(word_data)

def tag_insert(word_id, tag):
    if redis_c.zscore(word_id, tag) is None:
        print('add {0} {1}'.format(word_id, tag))
        redis_c.zadd(word_id, 1, tag)

def tag_upvote(word_id, tag):
    if redis_c.zscore(word_id, tag) is not None:
        redis_c.zincrby(word_id, tag)

def tag_downvote(word_id, tag):
    if redis_c.zscore(word_id, tag) is not None:
        redis_c.zincrby(word_id, tag, -1)

def tag_fetch(word_id, fetch_num):
    for (id, val) in redis_c.zrange(word_id, 0, fetch_num-1, desc=True, withscores=True):
        print(get_word(id.decode('utf-8')), val)

def update_fresh_rate():
    db.engine.execute(RAWQUERY['fresh_rate'])

def elapse_time():
    db.engine.execute(RAWQUERY['elapse_time'])#[0])
  #  db.engine.execute(RAWQUERY['elapse_time'][1])


def open_save_file(filename):
    try:
        f = open(os.path.join('app', 'static', filename + '.csv'), 'r')
        i = 0
        j = 0
        for line in f:
            try:
                w = line.partition(',')[0]
                word_search_insert(w)
            except Exception as e:
                print("duplicate {0}: {1}".format(type(e), e))
            i += 1
            if i > 100:
                i = 0
                j += 1
                print('{0}00th commit'.format(j))
    except IOError:
        print("could not open {0}".format(filename))
