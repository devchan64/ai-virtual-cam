import sys
import unittest

from src.app.whisper_window import (
    _collapse_adjacent_repeated_phrase_details,
    _coalesce_completed_sentences_for_staging,
    _final_sentence_diagnostic_flags,
    _normalized_text,
    _pending_overrun_reason,
    _pending_text_diagnostic_flags,
    _replacement_decision_reason,
    _should_stage_replacement_candidate,
    _sentence_output_delta,
    _sentences_are_revisions,
)


# These tracking cases are mined from accumulated .tmp/logs/avc-whisper.log* files.
# This module is a performance trend harness, not a pass/fail quality gate.
# unittest success only means the metric collection ran; the printed rates are the improvement targets.
TRACKING_TARGETS = {
    "revision": {"target_cases": 90, "target_rate": 0.90},
    "distinct": {"target_cases": 25, "target_rate": 0.95},
    "collapse": {"target_cases": 45, "target_rate": 0.90},
    "stability": {"target_cases": 10, "target_rate": 0.80},
    "replacement": {"target_cases": 11, "target_rate": 0.90},
    "pending": {"target_cases": 10, "target_rate": 0.90},
    "pending_quality": {"target_cases": 1, "target_rate": 1.00},
    "final_quality": {"target_cases": 8, "target_rate": 0.90},
    "translation_quality": {"target_cases": 8, "target_rate": 0.80},
    "coalesce": {"target_cases": 10, "target_rate": 1.00},
    "stage_candidate": {"target_cases": 4, "target_rate": 1.00},
    "duplicate_suppression": {"target_cases": 4, "target_rate": 1.00},
    "runtime_metrics": {"target_cases": 6, "target_rate": 1.00},
}

REVISION_TRACKING_CASES = [
    {'left': '예전에 2000년 중반부터 2010년대까지 미중이 싸우기 전까지만 해도 과거에 많은 연준부의장들이', 'right': '예전에 2000년 중반부터 2010년대까지 미중이 싸우기 전까지만 해도 과거에 많은 연준부의장들이 나와서 달러를', 'source': 'avc-whisper.log chunks 44-45'},
    {'left': '예전에 2000년 중반부터 2010년대까지 미중이 싸우기 전까지만 해도 과거에 많은 연준부의장들이 나와서 달러를', 'right': '예전에 2000년 중반부터 2010년대까지 미중이 싸우기 전까지만 해도 과거에 많은 연준부의장들이 나와서 달러를 홍보를', 'source': 'avc-whisper.log chunks 45-46'},
{'left': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는',
  'right': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전',
  'source': 'avc-whisper.log'},
 {'left': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전',
  'right': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전 반대의 사이클로',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠', 'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서', 'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서',
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리',
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도',
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도 굳이',
  'source': 'avc-whisper.log'},
 {'left': '재정적 프리미엄이', 'right': '재정적 프리미엄이 과거', 'source': 'avc-whisper.log'},
 {'left': '재정적 프리미엄이 과거', 'right': '재정적 프리미엄이 과거 수준으로 돌아가면서', 'source': 'avc-whisper.log'},
 {'left': '있었던 기간 프리미엄의 마이너스', 'right': '있었던 기간 프리미엄의 마이너스 영역이', 'source': 'avc-whisper.log'},
 {'left': '복귀가 되면서 미국', 'right': '복귀가 되면서 미국 국채금리는 떨어질', 'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오', 'right': '그래서 그 시나리오 대로라면', 'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오 대로라면', 'right': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은', 'right': '실제로 올해랑 작년에 한국 같은 케이스에서도', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도', 'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의',
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세',
  'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정',
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의',
  'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의',
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의 구조 자체를',
  'source': 'avc-whisper.log'},
 {'left': '바꾸는 모습들로', 'right': '바꾸는 모습들로 가져왔잖아요.', 'source': 'avc-whisper.log'},
 {'left': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는', 'right': '바꾸는 모습들로 가져왔잖아요.', 'source': 'avc-whisper.log'},
 {'left': '바꾸는 모습들로 가져왔잖아요.', 'right': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는 결국에.', 'source': 'avc-whisper.log'},
 {'left': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는 결국에.', 'right': '근데 문제는 결국에.', 'source': 'avc-whisper.log'},
 {'left': '세수가 많이 들어오면 정부가 할 수 있는', 'right': '세수가 많이 들어오면 정부가 할 수 있는 건 두 가지예요.', 'source': 'avc-whisper.log'},
 {'left': '세수가 많이 들어오면 정부가 할 수 있는 건 두 가지예요.', 'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지', 'source': 'avc-whisper.log'},
 {'left': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지', 'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는', 'source': 'avc-whisper.log'},
 {'left': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는',
  'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는 가지예요.',
  'source': 'avc-whisper.log'},
 {'left': '빚을 갚는다 빚을 줄인다 두', 'right': '빚을 갚는다 빚을 줄인다 두 번째는 아니야 투자를', 'source': 'avc-whisper.log'},
 {'left': '빚을 갚는다 빚을 줄인다 두 번째는 아니야 투자를 한다.', 'right': '빚을 줄인다 두 번째는 아니야 투자를 한다', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인', 'right': '투자를 하면 성장을 하는 요인인 거고 빚을', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을', 'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면', 'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는',
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두',
  'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두',
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고',
  'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고',
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고 한쪽에 몰빵할 수도',
  'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국', 'right': '있는 건데 지금 한국 같은', 'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국 같은', 'right': '있는 건데 지금 한국 같은 경우는.', 'source': 'avc-whisper.log'},
 {'left': '투자를 하겠다.', 'right': '경우는 투자를 하겠다.', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는', 'right': '미국 같은 경우는 일단은 빛은 연준보고', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고', 'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할',
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 안',
  'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 안',
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을',
  'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을',
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을 해준다면 반반을 하겠죠',
  'source': 'avc-whisper.log'},
 {'left': '투자도 하고 빚도 갚고 뭐 이런', 'right': '투자도 하고 빚도 갚고 뭐 이런 식으로 나누는 게', 'source': 'avc-whisper.log'},
 {'left': '지금 정부가 이제 기업들의', 'right': '지금 정부가 이제 기업들의 정부가 기업들의 세수가 들어왔을 때 할', 'source': 'avc-whisper.log'},
 {'left': '것 같아요 그러면 지금 ai 산업에는', 'right': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더', 'source': 'avc-whisper.log'},
 {'left': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더',
  'right': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더 계속 지속적인 투자가',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인', 'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두', 'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로',
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를',
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고',
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고 있는 국가',
  'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서', 'right': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을', 'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을', 'right': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을 하고 있잖아요.', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야', 'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을 투자를 하고',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을 투자를 하고',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에',
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에 들어오라고 하고',
  'source': 'avc-whisper.log'},
 {'left': '이런 생태를 할 수밖에', 'right': '이런 생태를 할 수밖에 없는', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속', 'right': '그런데 연준 쪽에서 금리를 계속 거죠', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 거죠', 'right': '그런데 연준 쪽에서 금리를', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를', 'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을', 'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금',
  'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금 이제 버거워',
  'source': 'avc-whisper.log'},
 {'left': '버거워지잖아요 트럼프', 'right': '버거워지잖아요 트럼프 받기가 조금 버거워지잖아요.', 'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의', 'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런', 'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을',
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을 때',
  'source': 'avc-whisper.log'},
 {'left': '기업들로 돌아가는 이익이라든지 이런', 'right': '기업들로 돌아가는 이익이라든지 이런 부분들에 대한', 'source': 'avc-whisper.log'},
 {'left': '제도적 개선들을 만들어낼', 'right': '제도적 개선들을 만들어낼 수 있는 부분들도 있을', 'source': 'avc-whisper.log'},
 {'left': '그걸 과거에는 연준이', 'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데', 'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데',
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의',
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할',
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고',
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는',
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는 거잖아요.',
  'source': 'avc-whisper.log'},
 {'left': '그럼 결국에는 재정의 역할이 커질 수밖에', 'right': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는', 'source': 'avc-whisper.log'},
 {'left': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는',
  'right': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는 상황이고',
  'source': 'avc-whisper.log'}]

DISTINCT_TRACKING_CASES = [
    {'left': '의장들이 나와서 달러를 홍보를 합니다', 'right': '빨라를 홍보를 합니다', 'source': 'avc-whisper.log chunk 48'},
    {'left': '빨라를 홍보를 합니다', 'right': '이게 뭘까', 'source': 'avc-whisper.log chunk 48'},
    {'left': '근데 우리가 그런 얘기하지 골적으로 얘기하지 않죠', 'right': '우리가 그런 얘기하지 않습니다', 'source': 'avc-whisper.log chunk 76'},
{'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도 굳이',
  'right': '재정적 프리미엄이',
  'source': 'avc-whisper.log'},
 {'left': '있었던 기간 프리미엄의 마이너스 영역이', 'right': '복귀가 되면서 미국', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세',
  'right': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.',
  'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.',
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정',
  'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국 같은 경우는.', 'right': '투자를 하겠다.', 'source': 'avc-whisper.log'},
 {'left': '수 있는 행태라고 보시면 되실', 'right': '것 같아요 그러면 지금 ai 산업에는', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고 있는 국가', 'right': '중국 AI 관련돼서', 'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을 하고 있잖아요.', 'right': '내가 1등 할 거야', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에 들어오라고 하고',
  'right': '이런 생태를 할 수밖에',
  'source': 'avc-whisper.log'},
 {'left': '이런 생태를 할 수밖에 없는', 'right': '그런데 연준 쪽에서 금리를 계속', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금 이제 버거워', 'right': '버거워지잖아요 트럼프', 'source': 'avc-whisper.log'},
 {'left': '기업들로 돌아가는 이익이라든지 이런 부분들에 대한', 'right': '제도적 개선들을 만들어낼', 'source': 'avc-whisper.log'},
 {'left': '볼 수 있는 시나리오 그럼 이게 딱히 뭐 그렇게 절망적으로 볼 상황은 근데 모르겠어요 어디까지나 이제 그런데 모르겠어요.',
  'right': '어디까지나 이론적인 부분인 거고',
  'source': 'avc-whisper.log'},
 {'left': '그러면서 시장금리 이렇게 흘러내렸던 게 일반적이었는데 왜냐하면 레버리지 구조의 경계 구조기',
  'right': '망가졌었고 연준이 나서서 얘를 구해줬었어요 그러면서 시장 구해줬어요.',
  'source': 'avc-whisper.log'},
 {'left': '망가졌었고 연준이 나서서 얘를 구해줬었어요 그러면서 시장 구해줬어요.',
  'right': '그러면서 시장금리 이렇게 흘러내렸던 게 일반적이었는데 왜냐하면 레버리지 구조의 경계 구조기 구조이기 때문에',
  'source': 'avc-whisper.log'},
 {'left': '높은 거예요 그래서 버티고 가자 쪽으로 가는 거니까 금리가 높아도 이쪽으로 돈이 계속 들어가다', 'right': '보니까 경기가 버티고', 'source': 'avc-whisper.log'},
 {'left': '이거는 위기가 나와봐야 하지 나와 봐야지 않은 거고 이거는 위기가 나와봐야지 아는 거고 너무 많이 바뀌고 이제 바뀌고 있는 산업의 경로기',
  'right': '때문에 돌아갈지',
  'source': 'avc-whisper.log'},
 {'left': '돈은 낮은 쪽에서 높은 쪽으로 쏠릴 수밖에 없어요 그리고 한국은행이 올해 금리 올린다고 하잖아요.', 'right': '근데 문제는 아무리', 'source': 'avc-whisper.log'},
 {'left': '그러면 원달러 원달러안율은 지금 1500원대 환율은 지금 1500원대 너무 높아 보이는데 이게 어느 순간 뉴노멀로 인식이 되고 1500원이 아니라 1600원',
  'right': '1700원으로도 얼마든지 갈',
  'source': 'avc-whisper.log'},
 {'left': '1700원으로도 얼마든지 갈 수 천육백 원 천칠백 있는 내러티비를 만들어낼 수 내로티비를 만들어 낼 수 있다는 거죠.',
  'right': '그래서 제가 최근에',
  'source': 'avc-whisper.log'},
 {'left': '그래서 제가 최근에 이제 가장 많이 받던 질문 봤던 질문 중 중 하나는 다시 뭐 예전에 우리 1300원 1200원 천삼백 원 천이백 원 이게 좀',
  'right': '일반적이지 않냐',
  'source': 'avc-whisper.log'},
 {'left': '비상식적이다 결국에 낮아질까 낮아질 수 있겠지 이런 기대감들은 조금 있어요 근데 제가 말씀드리고 싶은 건',
  'right': '이전에 경험해보지 못한',
  'source': 'avc-whisper.log'},
 {'left': '예전에 베이스 레벨이 1200원대가 베이스였다면 지금은 베이스 레벨이 천이백 원대가 베이스였다면 지금은 천오백 원대 1500원대 플러스 알파가 베이스 레벨일 수도 있겠다 라는 있겠다라는 생각이 있겠다는 생각이 채권 시장 있을 '
          '레벨일 수도 있겠다는 생각이 채권시장 정치적인 관계 정치적인 관계 그리고 이제 통화 정책 관계',
  'right': '통화정책 관계 정부의',
  'source': 'avc-whisper.log'},
 {'left': '정부의 관계 이런 모든 투자 사이클이라든지 이런 부분들에서 다 나타나고 있다는', 'right': '통화정책 관계 정부의 관계', 'source': 'avc-whisper.log'},
 {'left': '통화정책 관계 정부의 관계',
  'right': '정부의 관계 이런 모든 투자 사이클이라든지 이런 부분들에서 다 나타나고 있다는 왜냐하면 연준은 금리 이상',
  'source': 'avc-whisper.log'}]

COLLAPSE_TRACKING_CASES = [
    {"source": "2026-06-14 monitor chunk 936 repeated Chinese clause", "text": "这吃五里鸡王。香香香香香香香香。这吃五里鸡王。这吃五里鸡王。"},
    {"source": "2026-06-14 monitor chunk 947 repeated Chinese short clause", "text": "豆浆，豆浆，豆浆，豆浆。哇，好大一份啊。"},
{'source': 'avc-whisper.log', 'text': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.'},
 {'source': 'avc-whisper.log', 'text': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을'},
 {'source': 'avc-whisper.log', 'text': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을 해준다면 반반을 하겠죠'},
 {'source': 'avc-whisper.log', 'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이'},
 {'source': 'avc-whisper.log', 'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
          '위해서'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을 투자를 하고'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에'},
 {'source': 'avc-whisper.log',
  'text': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에 들어오라고 하고'},
 {'source': 'avc-whisper.log',
  'text': '예전에 베이스 레벨이 1200원대가 베이스였다면 지금은 베이스 레벨이 천이백 원대가 베이스였다면 지금은 천오백 원대 1500원대 플러스 알파가 베이스 레벨일 수도 있겠다 라는 있겠다라는 생각이 있겠다는 생각이 채권 시장 있을 '
          '레벨일 수도 있겠다는 생각이 채권시장 정치적인 관계 정치적인 관계 그리고 이제 통화'},
 {'source': 'avc-whisper.log',
  'text': '예전에 베이스 레벨이 1200원대가 베이스였다면 지금은 베이스 레벨이 천이백 원대가 베이스였다면 지금은 천오백 원대 1500원대 플러스 알파가 베이스 레벨일 수도 있겠다 라는 있겠다라는 생각이 있겠다는 생각이 채권 시장 있을 '
          '레벨일 수도 있겠다는 생각이 채권시장 정치적인 관계 정치적인 관계 그리고 이제 통화 정책 관계'},
 {'source': 'avc-whisper.log', 'text': '원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에'},
 {'source': 'avc-whisper.log', 'text': '원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에 밖에 없는'},
 {'source': 'avc-whisper.log', 'text': '원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에 밖에 없는 수밖에 없는 거죠 그리고 더 받을 수 밖에 없는 거죠 그리고 마지막으로'},
 {'source': 'avc-whisper.log', 'text': '되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런'},
 {'source': 'avc-whisper.log', 'text': '되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런 스페이스X라는 이런 대규모의 IPO 상장 같은 게'},
 {'source': 'avc-whisper.log', 'text': '되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런 스페이스X라는 이런 대규모의 IPO 상장 같은 게 지금 몇 개'},
 {'source': 'avc-whisper.log', 'text': '하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게'},
 {'source': 'avc-whisper.log', 'text': '하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게 과거처럼 내려가지는'},
 {'source': 'avc-whisper.log', 'text': '하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게 과거처럼 내려가지는 않을 거다'},
 {'source': 'avc-whisper.log', 'text': '내에서도 반도체와 반도체 제외 종목 간의 양극화들도 제외종목간의 양극화들도 극심해지고 있다는'},
 {'source': 'avc-whisper.log', 'text': '아마 정책당국의 고민도 그걸 것 같고 원달러 환율이 이렇게 안 떨어지다 보면 수출기업들은 굉장히 표면적으로는 수출 기업들은 굉장히 표면적으로는 좋긴'},
 {'source': 'avc-whisper.log',
  'text': '근데 내년의 성장률도 다 상향 조정 근데 내년에 성장률도 다 상향조정 시켜놨어요 기존의 조정시켜놨어요 기존의 내년 성장률은 방향 조정 1%대였어요 이거를 2.1%로 2.1%를 올렸고 물가도 마찬가지로 다'},
 {'source': 'avc-whisper.log',
  'text': '근데 내년의 성장률도 다 상향 조정 근데 내년에 성장률도 다 상향조정 시켜놨어요 기존의 조정시켜놨어요 기존의 내년 성장률은 방향 조정 1%대였어요 이거를 2.1%로 2.1%를 올렸고 물가도 마찬가지로 다 올려놨죠.'},
 {'source': 'avc-whisper.log', 'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한'},
 {'source': 'avc-whisper.log', 'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의'},
 {'source': 'avc-whisper.log', 'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데'},
 {'source': 'avc-whisper.log', 'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데 불과 일 년 육'},
 {'source': 'avc-whisper.log', 'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데 불과 일 년 육 개월 뒤에'},
 {'source': 'avc-whisper.log',
  'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데 불과 일 년 육 개월 뒤에 그림이었는데 불과 1년 6개월 뒤에 바뀐 점들이 몇 '
          '가지가'},
 {'source': 'avc-whisper.log',
  'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데 불과 일 년 육 개월 뒤에 그림이었는데 불과 1년 6개월 뒤에 바뀐 점들이 몇 '
          '가지가 있어요'},
 {'source': 'avc-whisper.log',
  'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 잠재 성장률의 그림이었는데 불과 일 년 육 개월 뒤에 그림이었는데 불과 1년 6개월 뒤에 바뀐 점들이 몇 가지가 있어요 일단 인구는'},
 {'source': 'avc-whisper.log',
  'text': '이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 잠재 성장률의 그림이었는데 불과 일 년 육 개월 뒤에 그림이었는데 불과 1년 6개월 뒤에 바뀐 점들이 몇 가지가 있어요 일단 인구는 안 '
          '바뀌었어요.'},
 {'source': 'avc-whisper.log', 'text': '줄 중에 여섯 가지 끌어내려 올렸던 중에 다섯 가지가 지금 방향성 들을 바꾸기 방향성들을 바꾸기 시작했다는 거죠'},
 {'source': 'avc-whisper.log', 'text': '많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적'},
 {'source': 'avc-whisper.log', 'text': '많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적 사이클을 계속 펌프질을 하고'},
 {'source': 'avc-whisper.log', 'text': '많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적 사이클을 계속 펌프질을 하고 있는'},
 {'source': 'avc-whisper.log', 'text': '그러면 지금 현재만 초호황 시장이거든요 그럼 지금 현재만 놓고 보면 5개월, 3개월, 6개월 모건 머건스테인에서 나온 머건스테인에서 나온 것처럼 12개월 동안에 매출에 대한'},
 {'source': 'avc-whisper.log',
  'text': '그러면 지금 현재만 초호황 시장이거든요 그럼 지금 현재만 놓고 보면 5개월, 3개월, 6개월 모건 머건스테인에서 나온 머건스테인에서 나온 것처럼 12개월 동안에 매출에 대한 수요와 EPS 성장 반도체'},
 {'source': 'avc-whisper.log', 'text': '그리고 이미 27년도 까지 27년도까지 매출은 책정이'}]


REPLACEMENT_TRACKING_CASES = [
    {
        "staged": "1억을 넣었을 때 2000만원이 깨지는 천만원에서 20% 빠졌을 때 200이 깨지는 느낌",
        "candidate": "이런 것들을 계속해서 좀 충격도 한번 받아보고 얼마나 견뎌낼 수 있는지 그거는 사실 스스로도 몰라요.",
        "expected": "open_korean_clause",
        "confirmations": 4,
        "source": "2026-06-13 30m monitor chunks 7-11",
    },
    {
        "staged": "이 두 직업은",
        "candidate": "그런데 보면 최치PD가 등장하기 전까지는 이",
        "expected": "open_korean_clause",
        "source": "2026-06-13 30m monitor chunks 54-55",
    },
    {
        "staged": "특히 스웨덴의 러브블 이란 회사가 지금 제일 잘 나갑니다",
        "candidate": "이걸 쓰시면 실리콘밸리 레덴의 러브오블이라는 회사가 지금 제일 잘 나갑니다.",
        "expected": "partial_preserve",
        "source": "2026-06-13 30m monitor chunks 157-158",
    },
    {
        "staged": "그런데 공장에서 기계들이 스팀 엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도예요.",
        "candidate": "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다",
        "expected": "partial_preserve",
        "source": "2026-06-13 30m monitor chunks 315-316",
    },
    {
        "staged": "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다",
        "candidate": "바로 다음주 수요일부터 되는 50년 정도가 더 걸렸습니다.",
        "expected": "partial_preserve",
        "source": "2026-06-13 30m monitor chunks 316-317",
    },
    {
        "staged": "근데 우리가 그런 얘기하지 골적으로 얘기하지 않죠",
        "candidate": "우리가 그런 얘기하지 않습니다",
        "expected": "partial_revision",
        "source": "avc-whisper.log chunk 76",
    },
    {
        "staged": "바로 다음주 수요일부터 되는",
        "candidate": "바로 다음 주 수요일부터 되는 건 절대로 아닙니다.",
        "expected": "open_korean_clause",
        "source": "2026-06-13 30m monitor chunk 317",
    },
    {
        "staged": "저녁에 퇴근하고",
        "candidate": "저녁에 퇴근하고 집에 와서 야 나",
        "expected": "open_korean_clause",
        "source": "2026-06-13 30m monitor chunk 821",
    },
    {
        "staged": "타자기로 글을 쓸",
        "candidate": "타자기로 글을 쓸 때",
        "expected": "open_korean_clause",
        "source": "2026-06-13 30m monitor open clause",
    },
    {
        "staged": "Currently, in the robot world, I worked as I've never",
        "candidate": "It's my first",
        "expected": "open_latin_clause",
        "source": "whisper-monitor-20260613-5 chunks 119-120",
    },
    {
        "staged": "Like, R2D2 would beep at you and it's hard to figure out what he's talking about, to be able to translate,",
        "candidate": "there are probably, I don't know, three to five robots in industry for every one that's a personal robot.",
        "expected": "open_latin_clause",
        "source": "whisper-monitor-20260613-5 chunk 433",
    },
    {
        "staged": "第一期有吃过。",
        "candidate": "第一期我吃过哎不对第一期我去过没吃到对没买到卖光了",
        "expected": "unconfirmed_cjk",
        "confirmations": 2,
        "source": "2026-06-15 Chinese monitor 20s chunk 131",
    },
]


PENDING_TRACKING_CASES = [
    {
        "pending": "So, as much as the exchange of emotions is important, especially when when and especially when people meet and talk, one of the core of the exchange key to emotional exchange is nodding their head nodding your head, making your nodding and making a bright face, and Ariana is nodding her head, making her face look",
        "chunks": 7,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-5 chunk 368",
    },
    {
        "pending": "so as far as SpaceX the reason that there hasn't been a huge number of a big improvement in in the space industry because it is there's such a significant amount of capital that's needed to start a rocket company, and it's a very difficult technical challenge and the number of people that really understand rocketry in",
        "chunks": 13,
        "expected": "long_no_boundary",
        "source": "avc-whisper.log chunk 118",
    },
    {
        "pending": "He has thrived in Silicon Valley, one of the co-founders of PayPal, the online payments company that eBay bought for $1.5",
        "chunks": 4,
        "expected": "",
        "source": "avc-whisper.log chunk 24",
    },
    {
        "pending": "So even though it's only 2.5 two and a half gallons gasoline, of energy content of gasoline, energy content goes really far compared with, you know, if that was, I think it's taken a while for the industry to come around to this point, but I think it's largely, at this point, it's almost become conventional wisdom that",
        "chunks": 10,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 249",
    },
    {
        "pending": "And there's just no way that we could afford a billion dollars to make a giant car plant that would make hundreds of thousands of cars a year, because that's the kind of volume you have to get to",
        "chunks": 8,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 310",
    },
    {
        "pending": "Okay, so how's that going, reaching scale and being able to create a marketing, business plan that will enable you to reach a large audience and create and continue the development of the technology that will",
        "chunks": 9,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 331",
    },
    {
        "pending": "Now, for the first time in Korea, to be able to legally drive a friend of mine happened to drive a Tesla for the car on the street, and coincidentally, a close friend was riding a Tesla, so the day he downloaded the software on the day it was allowed so they allowed me to use the software and they let me ride for about an hour",
        "chunks": 6,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 733 language-mismatch risk",
    },
    {
        "pending": "But if you do it with self-driving, by self-driving, you can fold it with a side into a side mirror and enter it yourself, so you can mirror and put it in by yourself, you a 1cm gap, It's almost 1cm in diameter, so you can put a lot of cars in it, so and when I say that I will make a self-driving",
        "chunks": 6,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 993 language-mismatch risk",
    },
    {
        "pending": "Then, as the atomic bomb came out, science and science and technology always make us feel aware of the fact that it's there was a sense of awareness that science and technology are not always the only thing that makes us good, and there's an environmental pollution story, and ultimately, in",
        "chunks": 4,
        "expected": "long_no_boundary",
        "source": "whisper-monitor-20260613-4 chunk 1203 language-mismatch risk",
    },
    {
        "pending": "this pending text has grown beyond the normal pending size and now it finally has a sentence ending marker that can be committed safely enough for real-time translation while still preserving enough context for downstream translation quality checks.",
        "chunks": 8,
        "expected": "with_end_mark",
        "source": "synthetic completed overrun",
    },
]

PENDING_QUALITY_TRACKING_CASES = [
    {
        "pending": (
            "干里面得这么吃，把干里面盛勺子里，进我这吃的就是像那觉得乒乓球一样，"
            "干面得这么吃，把干面盛勺子里，进去再快点汤手一样，干面得这么吃，"
            "把干面盛勺子里，进去再快点汤，干粒面得这么吃，把干粒面盛勺子里，进去再快点汤，"
        ),
        "language": "zh",
        "chunks": 4,
        "expected_flags": {"cjk_repeated_ngram"},
        "source": "2026-06-15 16s/1s Chinese monitor pending chunks 26-28",
    },
]

STABILITY_TRACKING_SEQUENCES = [
    [
        "이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는",
        "이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전",
        "이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전 반대의 사이클로",
    ],
    [
        "투자를 하면 성장을 하는 요인인",
        "투자를 하면 성장을 하는 요인인 거고 빚을",
        "투자를 하면 성장을 하는 요인인 거고 빚을 갚으면",
        "투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는",
    ],
    [
        "기업들로 돌아가는 이익이라든지 이런",
        "기업들로 돌아가는 이익이라든지 이런 부분들에 대한",
    ],
    [
        "트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기",
        "트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의",
        "트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을",
    ],
    [
        "내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고",
        "내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이",
        "내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을",
    ],
    [
        "원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에",
        "원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에 밖에 없는",
        "원화도 당연히 약세압력을 원래도 있는데 추가적으로 더 받을 수 추가적으로 더 받을 수밖에 밖에 없는 수밖에 없는 거죠 그리고 더 받을 수 밖에 없는 거죠 그리고 마지막으로",
    ],
    [
        "되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런",
        "되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런 스페이스X라는 이런 대규모의 IPO 상장 같은 게",
        "되면서 워낙 약세 일정 부분 조인을 하고 있는 거고 스페이스X라는 스페이스 x 라는 이런 스페이스X라는 이런 대규모의 IPO 상장 같은 게 지금 몇 개",
    ],
    [
        "하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게",
        "하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게 과거처럼 내려가지는",
        "하면 1500원대에 1500원대 굉장히 높은 레벨이긴 1,500원대 굉장히 높은 레벨이긴 한데 이게 과거처럼 내려가지는 않을 거다",
    ],
    [
        "이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한",
        "이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의",
        "이게 24년도 12월달에 한국은행이 이게 24년도 12월 달에 한국은행이 발표한 잠재성장률의 일월 달에 한국은행이 발표한 잠재 성장률의 그림이었는데",
    ],
    [
        "많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적",
        "많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적 사이클을 계속 펌프질을 하고",
        "많이 거쳐도 이거를 재정으로 쓰지 않고 다 투자로 이제 쏟아 부으면서 쏟아부으면서 이런 이제 산업적 사이클을 계속 펌프질을 하고 있는",
    ],
]


REVISION_TRACKING_CASES.extend([
    {"left": "그렇죠", "right": "스테이블 코인인가요", "source": "2026-06-13 monitor chunks 1114"},
    {"left": "스테이블 코인인가요", "right": "그렇죠", "source": "2026-06-13 monitor chunks 1114"},
    {"left": "그게 유럽입니다", "right": "그게 유럽 모형이에요", "source": "2026-06-13 monitor chunk 910"},
    {"left": "그게 유럽 모형이에요", "right": "없어 아주", "source": "2026-06-13 monitor chunk 911"},
    {"left": "그러니까 미국이 함부로 그걸 안 하는 거죠", "right": "그게 이런 모형이에요", "source": "2026-06-13 monitor chunk 913"},
    {"left": "저는 이게 상당히 걱정이 돼요", "right": "왜냐하면 미국인들 돈만 들어가는 게 아니라 전세계 돈이 다 빨려 들어가겠죠", "source": "2026-06-13 monitor chunk 1176"},
])

DISTINCT_TRACKING_CASES.extend([
    {"left": "지금 코스피도 많이 오르고", "right": "근데 중요한 건 그거는 반도체 국한된 얘기잖아요", "source": "2026-06-13 monitor chunk 878"},
    {"left": "근데 중요한 건 그거는 반도체 국한된 얘기잖아요", "right": "반도체 산업의 종사자들은 늘어날 수 있고 투자가 늘어날 수 있다고", "source": "2026-06-13 monitor chunk 881"},
    {"left": "결국에 돈의 문제예요", "right": "재정이 확보가 안되고 재정이 확보가 안되니까 연구개발이 안 되잖아요", "source": "2026-06-13 monitor chunk 933"},
    {"left": "근데 요새는 다른 거 같아요", "right": "이 신용화폐 근데 요새는 다른 것 같아요", "source": "2026-06-13 monitor chunk 1006"},
    {"left": "채권사는 플랫폼을 만들어 놓을 거예요", "right": "그 플랫폼에서 거기서 바로바로 거래를 할 수 있게끔", "source": "2026-06-13 monitor chunk 1188"},
    {"left": "아니요", "right": "이거는 이미 트렌드화가 돼서 5년 10년은 더 갈 것 같죠", "source": "2026-06-13 monitor chunk 1247"},
])

REVISION_TRACKING_CASES.extend([
    {"left": "이 두 직업은", "right": "이 두 직업은 그런데 보면 최치PD가 등장하기 전까지는", "source": "2026-06-13 30m monitor chunks 54-56"},
    {"left": "특히 스웨덴의 러브블 이란 회사가 지금 제일 잘 나갑니다", "right": "이걸 쓰시면 실리콘밸리 레덴의 러브오블이라는 회사가 지금 제일 잘 나갑니다.", "source": "2026-06-13 30m monitor chunks 157-158"},
    {"left": "그런데 공장에서 기계들이 스팀 엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도예요.", "right": "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다", "source": "2026-06-13 30m monitor chunks 315-316"},
    {"left": "엔진이 아닌 전기로 돌아가기 시작한 건 사실 1920년도 에요 50년 정도가 더 걸렸습니다", "right": "바로 다음주 수요일부터 되는 50년 정도가 더 걸렸습니다.", "source": "2026-06-13 30m monitor chunks 316-317"},
    {"left": "교통사고라는 게 그 데미지가 너무 크기 때문에 안전벨트 안전벨트라는 불편함을 감수하면서 라는 확률이 매우 낮은데도 벨트라는 거예요", "right": "확률이 매우 낮은데도 벨트를 매는 거예요", "source": "2026-06-13 30m monitor chunks 820-821"},
])

REVISION_TRACKING_CASES.extend([
    {"left": "새로운 물리학 이론을", "right": "새로운 물리학 이론을 만들어낼 수 있을까?", "source": "2026-06-13 30m monitor chunk 765"},
    {"left": "자연의 법칙은 이렇게 해도 충분히 바꿀", "right": "자연의 법칙은 이렇게 해도 충분히 바꿀 수 있다고 생각합니다.", "source": "2026-06-13 30m monitor forced revision"},
    {"left": "앞으로 적어도 30년 40년 동안 여러분들께서 일을 하시고 싶으셔야", "right": "앞으로 적어도 30년 40년 동안 여러분들께서 일을 하시고 싶으셔야 됩니다", "source": "2026-06-13 30m monitor forced revision"},
    {"left": "비행기에서는 다 꺼버리고 디지털 디속스를 하고 10시간 12시간 비행기 타다", "right": "비행기에서는 다 꺼버리고 디지털 디톡스를 하고 10시간 12시간 비행기를 타다가", "source": "2026-06-13 30m monitor open clause revision"},
])

DISTINCT_TRACKING_CASES.extend([
    {"left": "그 아래 3-5% 정도", "right": "인플루언서, 유명한 사람들, 연예인들 그리고 나머지 95%", "source": "2026-06-13 30m monitor chunk 861"},
    {"left": "그리고 아무도 모를 때는 그냥 해보시면 되는 것", "right": "기계가 잘하는 거 가지고 인간이 경쟁하는 건 무모한 짓이에요.", "source": "2026-06-13 30m monitor chunk 1135"},
    {"left": "AI가 점점점 확장이 좀 확장이 되면서", "right": "그럼 어떻게 되죠?", "source": "2026-06-13 30m monitor chunk 424"},
    {"left": "앞으로 산업이 어떻게 새롭게 재편될지 그것도", "right": "이 모든 것은 저의 개인적인 생각입니다", "source": "2026-06-13 30m monitor chunk 837"},
])

COLLAPSE_TRACKING_CASES.extend([
    {"source": "2026-06-13 30m monitor chunk 98", "text": "무나하지 않나요? 화성연료를 켠거에요. 우아하지 않나요?"},
    {"source": "2026-06-13 30m monitor chunk 133", "text": "밀어버린 거죠 건재하죠 건지하죠?"},
    {"source": "2026-06-13 30m monitor chunk 272", "text": "생각보다 핵융합은 초기 건설 비용 때문에 비싼 에너지원이에요. 생각보다 핵융합은 초기 건설 비용 때문에 비싼 에너지원이에요."},
])

COLLAPSE_TRACKING_CASES.extend([
    {"source": "2026-06-13 monitor chunk 1111", "text": "그렇다면은 돈은 계속 풀어야 되는데 그렇다면 돈은 계속 풀어야 되는데 마지막 남은"},
    {"source": "2026-06-13 monitor chunk 1163", "text": "이 스테이블 코인은 새로운 화폐의 탄생 이라고 탄생이라고 보셔야 돼요."},
    {"source": "2026-06-13 monitor chunk 1212", "text": "왜냐하면 우리는 종이돈을 가지고서 맡겨서 스테이블콘 이라는 새로운 아바타 돈을 돈을 만들 수 있고 사실 내"},
    {"source": "2026-06-13 monitor chunk 1229", "text": "보면 최단의 웰스, 부호와 화폐의 관점에서 5년 10년의 걸음을 화폐 활용도를 화폐 활용도를 높이려면"},
    {"source": "2026-06-13 monitor chunk 1238", "text": "그러면서 당연히 부의 양극화는 더 심화되는 돈을 이용해가지고 정부가 어떻게 돈을 이용해서 정부가 어떻게 보면 자산시장 사재기에 더 집중화시키고 있는 있는 전략일"},
])

REPLACEMENT_TRACKING_CASES.extend([
    {
        "staged": "这是我的台湾的车牌判。",
        "candidate": "的个湾的吃排饭三。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 monitor chunks 47 short CJK churn",
    },
    {
        "staged": "还宽零零。",
        "candidate": "其有没？",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 monitor chunks 48-49 short CJK churn",
    },
    {
        "staged": "好像有没？",
        "candidate": "对对。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 monitor chunks 50-51 short CJK churn",
    },
    {
        "staged": "哎，汤姆再见喽台。",
        "candidate": "哎，汤姆再见喽，台湾见。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 monitor chunk 73 revision candidate before convergence",
    },
    {
        "staged": "小吃街而在成都CT walk的情况下，就是你每走一段都觉得闻到各种不同香味的辣椒扑鼻而来。",
        "candidate": "而当。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log chunk 313 long CJK sentence replaced by short fragment",
    },
    {
        "staged": "然后这个老板极力推荐他自己弄的辣椒粉，配上这个。",
        "candidate": "假。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log chunk 317 long CJK sentence replaced by one-character fragment",
    },
    {
        "staged": "讲其实CCB这种东西使用寿命都不太长久，最主要也是因为市场价炒的太高了，感觉性价比也不高。",
        "candidate": "对当下。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.1 chunk 299 confirmed-ish long CJK replaced by short tail",
    },
    {
        "staged": "价比也不高，对，当下我是有点被劝退，后面还去看了衣服，因为晚上想要去蹦迪，但是反而被他家暴着吸引了注意力。",
        "candidate": "其实这。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.1 chunk 302 long CJK replaced by short tail",
    },
    {
        "staged": "是单脆皮年轻人，就是我和赵周丽梅走一段路，就在会，唉声叹气然。",
        "candidate": "单干脆皮年轻人就是我和周苏妮妹走一段路进，咱们唉声叹气，而后来实在受不了了，直接。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log chunk 306 long CJK churn",
    },
    {
        "staged": "我和赵苏，你每走一段路进，咱们唉声叹气，然后后来实在受不了了，直接跑去浴约按摩这两只。",
        "candidate": "唉，声叹气，然后来实在受不了了，直接跑去浴约按摩，这两只猫真的很活泼，从外面打架。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log chunk 308 long CJK churn",
    },
    {
        "staged": "而直接跑去预约按摩，这两只猫真的很活泼，从外面打架打到猫砂盆里面还在打按。",
        "candidate": "两只猫真的很活泼和外面打架，打到猫砂盆里面，还在打按摩店的底下有个小吃街，而在。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log chunk 310 long CJK churn",
    },
    {
        "staged": "他们这里的外卖呢选择非常非常的多。",
        "candidate": "要",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.1 chunk 101 stable Chinese sentence replaced by one-character fragment",
    },
    {
        "staged": "就在这里，野餐，今太阳要来洗。",
        "candidate": "那 个 是",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.3 chunk 15716 unprocessed short CJK replacement",
    },
    {
        "staged": "洗吹头发天呐，每次就是来，不然做什么头发护理。",
        "candidate": "发，所以呢每次就是来不管做什么头发护理呢，他们都会就是。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.3 chunk 15721 unprocessed long CJK churn",
    },
    {
        "staged": "有没有有有有没有？",
        "candidate": "The是the.",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.4 chunk 14055 zh language-mismatch churn",
    },
    {
        "staged": "美好，baby, i need you.",
        "candidate": "I love feeling feeleling baby, baby you only.",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.4 chunk 14082 zh mixed-latin churn",
    },
    {
        "staged": "机记。",
        "candidate": "As the mentionnearly.",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.5 chunk 12127 zh language-mismatch churn",
    },
    {
        "staged": "就下了将。",
        "candidate": "Two shot ted seventy in the part three.",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 avc-whisper.log.5 chunk 12153 zh language-mismatch churn",
    },
    {
        "staged": "我上次发现的都。",
        "candidate": "继续吃，等下吃完再去下。",
        "expected": "unconfirmed_cjk",
        "age": 3,
        "source": "2026-06-14 30m monitor chunk 104 aged short CJK suppression release",
    },
    {
        "staged": "来看看吉普力哦，这是什么？",
        "candidate": "可爱哦，好。",
        "expected": "unconfirmed_cjk",
        "age": 3,
        "source": "2026-06-14 30m monitor chunk 121 short CJK candidate remains suppressed",
    },
    {
        "staged": "厉害的吧，应应该。",
        "candidate": "厉害的宝宝应该会喜欢我，刚刚。",
        "expected": "unconfirmed_cjk",
        "source": "2026-06-14 30m monitor chunk 74 short CJK candidate suppressed",
    },
])


STAGE_CANDIDATE_TRACKING_CASES = [
    {
        "staged": "我上次发现的都。",
        "candidate": "爸爸妈。爸。",
        "age": 2,
        "max_age": 3,
        "expected": False,
        "source": "2026-06-14 30m monitor chunk 101 short candidate remains suppressed",
    },
    {
        "staged": "我上次发现的都。",
        "candidate": "继续吃，等下吃完再去下。",
        "age": 2,
        "max_age": 3,
        "expected": False,
        "source": "2026-06-14 30m monitor chunk 104 before max age",
    },
    {
        "staged": "我上次发现的都。",
        "candidate": "继续吃，等下吃完再去下。",
        "age": 3,
        "max_age": 3,
        "expected": True,
        "source": "2026-06-14 30m monitor chunk 104 aged growth release",
    },
    {
        "staged": "来看看吉普力哦，这是什么？",
        "candidate": "可爱哦，好。",
        "age": 3,
        "max_age": 3,
        "expected": False,
        "source": "2026-06-14 30m monitor chunk 121 short candidate remains suppressed",
    },
    {
        "staged": "厉害的吧，应应该。",
        "candidate": "厉害的宝宝应该会喜欢我，刚刚。",
        "age": 0,
        "max_age": 3,
        "expected": False,
        "source": "2026-06-14 30m monitor chunk 74 early short candidate suppressed",
    },
]


TRANSLATION_OBSERVED_QUALITY_CASES = [
    # These are observed output samples, not live model assertions. They are a
    # small regression corpus for comparing translation backends on the same input.
    {
        "category": "named_entity",
        "source_language": "zh",
        "target_language": "ko",
        "source": "说呢我来重庆，其实我挺怕的。",
        "observed": "제가 춘천에 왔을 때, 저는 정말 두려워했습니다.",
        "required_any": {"충칭", "중경"},
        "forbidden_any": {"춘천"},
        "case_source": "2026-06-14 monitor zh->ko Chongqing mistranslation",
    },
    {
        "category": "service_name",
        "source_language": "zh",
        "target_language": "ko",
        "source": "第一个呢要登陆的呢就是滴滴，滴滴呢就是来中国，你要搭车的话，你就可以搭滴滴。",
        "observed": "첫 번째 착륙은滴滴,滴滴는 중국으로 오는 것입니다. 당신이 차를 타고 있다면, 당신은滴滴을 타고 갈 수 있습니다.",
        "required_any": {"滴滴", "디디"},
        "forbidden_any": {"착륙"},
        "case_source": "2026-06-14 monitor zh->ko Didi mistranslation",
    },
    {
        "category": "service_name",
        "source_language": "zh",
        "target_language": "ko",
        "source": "另外一个你要到录的app呢，就是那个美团外卖。",
        "observed": "또 다른 앱은 미국 유출장소입니다.",
        "required_any": {"메이퇀", "美团"},
        "forbidden_any": {"미국", "유출장소"},
        "case_source": "2026-06-14 monitor zh->ko Meituan mistranslation",
    },
    {
        "category": "colloquial_term",
        "source_language": "zh",
        "target_language": "ko",
        "source": "面可是快速面就是它会比较q一点，这个呢是比快速。",
        "observed": "하지만 가속면은 q을 조금 더 비교할 수 있고, 이면은 가속보다 더 빠르다.",
        "required_any": {"쫄깃", "탄력", "Q", "큐"},
        "forbidden_any": {"가속"},
        "case_source": "2026-06-14 monitor zh->ko colloquial q mistranslation",
    },
    {
        "category": "acceptable_baseline",
        "source_language": "zh",
        "target_language": "ko",
        "source": "如果你们来中国旅游呢，你们要登录好几个app第一。",
        "observed": "중국을 여행할 때 먼저 여러 앱에 접속해야 합니다.",
        "required_all": {"중국", "앱"},
        "forbidden_any": set(),
        "case_source": "2026-06-14 monitor zh->ko acceptable baseline",
    },
    {
        "category": "domain_term",
        "source_language": "zh",
        "target_language": "ko",
        "source": "卷卷头前前面呢，他还帮我做了一个非常蓬松的刘海给。",
        "observed": "이 책 앞에는 그가 저에게 아주 느슨한 해양을 만들어주었습니다.",
        "required_any": {"앞머리", "머리"},
        "forbidden_any": {"책", "해양"},
        "case_source": "2026-06-14 avc-whisper.log.3 zh->ko hairstyle mistranslation",
    },
    {
        "category": "domain_term",
        "source_language": "zh",
        "target_language": "ko",
        "source": "日穿搭衣服呢是前几天买的裤子呢，也是本地的一个牌。",
        "observed": "이 옷은 며칠 전에 구입한 바둑이고, 지역 카드입니다.",
        "required_any": {"바지", "옷"},
        "forbidden_any": {"바둑", "카드"},
        "case_source": "2026-06-14 avc-whisper.log.3 zh->ko clothing mistranslation",
    },
    {
        "category": "acceptable_baseline",
        "source_language": "zh",
        "target_language": "ko",
        "source": "他们这里的外卖呢选择非常非常的多。",
        "observed": "이곳의 배달 선택지는 매우 많습니다.",
        "required_all": {"배달", "많"},
        "forbidden_any": set(),
        "case_source": "synthetic acceptable baseline",
    },
]


DUPLICATE_SUPPRESSION_TRACKING_CASES = [
    {
        "committed": "漫步下号里老街巷，触摸着重庆的旧时光；再搭乘长江索道，穿梭在两江上空， 皇冠大扶梯，超多层立交桥，还有令人难忘的绝美夜景和数也数不尽的江湖美食。今天就让我们奔赴一场山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。",
        "candidate": "当你看着满街霓虹点亮这座赛博山城的时候，味 山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。漫步下号里老街巷，触摸着重庆的旧时光。再搭乘长江索道，穿梭在两江上空，眼底高楼林立的错落感与重庆的老字形成了鲜明的对比。",
        "expected": "",
        "source": "2026-06-14 avc-whisper.log chunk 8 Chinese internal committed overlap",
    },
    {
        "committed": "漫步下号里老街巷，触摸着重庆的旧时光；再搭乘长江索道，穿梭在两江上空， 皇冠大扶梯，超多层立交桥，还有令人难忘的绝美夜景和数也数不尽的江湖美食。今天就让我们奔赴一场山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。 当你看着满街霓虹点亮这座赛博山城的时候，味 山城盛宴，行程与美食双双拉满，体验一下当轻轨吃进嘴里是一种什么感觉。漫步下号里老街巷，触摸着重庆的旧时光。再搭乘长江索道，穿梭在两江上空，眼底高楼林立的错落感与重庆的老字形成了鲜明的对比。 一碗劲道的重庆小面，一条焦香的巫山烤鱼，一锅火辣的美蛙鱼头，重庆的每一道美食都能在你 都淋漓的错落感，与重庆的老字形成了鲜明的对比。当你看着满街霓虹点亮这座赛博山城的时候，味道晕头转向的你，才会发现乌都真正的灵魂藏在烟火弥漫的后厨中。",
        "candidate": "山水有灵，十味留香， 赛博山城的时候，味道晕头转向的你，才会发现乌都真正的灵魂藏在烟火弥漫的后厨中。一碗劲道的重庆小面，一条焦香的巫山烤鱼，一锅火辣的美蛙鱼头。重庆的每一道美食都能在你饥肠辘辘的时候把你拯救回来。",
        "expected": "",
        "source": "2026-06-14 avc-whisper.log chunk 20 Chinese late internal committed overlap",
    },
    {
        "committed": "卖小饰品的，我买了个帽子，觉得非常的可爱，很喜 挺洋气的，主要还是我喜欢的KT酱，不错。开心，走吧。这边。他买的好看帽子，开心了你看。你高高。变成导游了。白鹿来过。我觉得这边还是非常好逛的，我非常的开心。他有很多的文创店、礼品店呀，你看还有。卖小饰品的，我买了个帽子，觉得非常的可爱，很喜欢。 这家店是中午两点就关 的可爱，很喜欢，还有很多点心啊，咖啡啊，半手里，好多东西，我觉得非常值得一逛。而且景色也是非常漂亮，就是雾都嘛，没有蓝天哦，都是白茫茫的一片。逛完了，真是又累又饿的。我们去吃一个重庆人的重口味吧，合金火爆",
        "candidate": "这家店是中午两点就关门了，如果上午去下号里逛的话，记得要控制好时间 在半手里好多东西，我觉得非常值得一逛。而且景色也是非常漂亮。就是雾都嘛，没有蓝天哦，都是白茫茫的一片。逛完了真是又累又饿的。我们去吃一个重庆人的重口味吧，何记火爆。这家店是中午两点就关门了。如果上午去夏号里逛的话，记得要控制好时间哟。我看他都有什么菜啊。",
        "expected": "",
        "source": "2026-06-14 avc-whisper.log chunk 577 Chinese repeated committed food route context",
    },
    {
        "committed": "值得一逛。而且景色也是非常漂亮，就是雾都嘛，没有蓝天哦，都是白茫茫的一片。逛完了，真是又累又饿的。我们去吃一个重庆人的重口味吧，合金火爆。 这家店是中午两点就关门了，如果上午去下号里逛的话，记得要控制好时间 在半手里好多东西，我觉得非常值得一逛。而且景色也是非常漂亮。就是雾都嘛，没有蓝天哦，都是白茫茫的一片。逛完了真是又累又饿的。我们去吃一个重庆人的重口味吧，何记火爆。这家店是中午两点就关门了。如果上午去夏号里逛的话，记得要控制好时间哟。我看他都有什么菜啊。 火爆黄喉，火爆肥肠，火爆腰花，火爆鱿鱼，火爆猫肚，火爆藕丁，火爆土豆，火爆鳝鱼，火爆凉粉，火爆 逛完了，真是又累又饿的。我们去吃一个重庆人的重口味吧。何记火爆。这家店是中午两点就关门了。如果上午去下号里逛的话，记得要控制好时间哟。我看它都有什么菜啊。火爆黄喉，火爆肥肠，火爆腰花，火爆鱿鱼，火爆猫肚，火爆藕丁，火爆土豆，火爆鳝鱼，火爆凉粉，火爆牛蛙。 长得都一样 记得叫控制好时间哟。我看他都有什么菜啊。火爆黄喉火爆肥肠火爆腰花火爆鱿鱼火爆猫肚火爆藕丁火爆土豆火爆鳝鱼火爆凉粉火爆牛蛙。报菜名呢，跟着。是哪个火爆？这么火爆啊。全是火爆，绝了！我的天呀。你们看这个菜，哇，太有食欲了。长得都一样不？ 全是火爆，点名火爆鱿鱼火爆黄 火爆鱿鱼，火爆猫头，火爆藕丁，火爆土豆，火爆鳝鱼，火爆凉粉，火爆牛蛙。报菜名呢，跟着。是哪个火爆？这么火爆啊。全是火爆，绝了，我的天呀。你们看这个菜，我太有食欲了。长得一样不？过对，长得有点一样。全是火爆，点了一火爆鱿鱼，火爆黄喉，火爆土豆。 来这儿就是 cook cook 鱿鱼火爆黄河，火爆土豆。本来点了火爆藕丁，然后藕丁没了，所以换成土豆了。土豆脑袋只能吃土豆了。是的。来这儿就是苦苦干饭的。哎，他为什么不能炒一个那种全家福啊？这样每个菜都可以吃到了。还有道理啊，你去提提建议。火爆鱿鱼。 它是那种酱 火爆鱿鱼，我辣到汗毛都立起来了。哇，不行，喝水就不好吃了。忍住。啊，辣懵了，孩子已经，一口完了，下线了。不是鱿鱼都能炒到这么辣吗？它是那种酱香辣的。 那个硬硬的感觉都没有，软Q 那个硬硬的感觉都对，软Q 是，就是很辣，但真的很爽。我刚偷吃了一个，确实是这样。锅气十足，里面配菜有洋葱、尖椒，还有一堆辣椒。这个洋葱看着就很香。这果然是重庆的辣度了啊。我回。咋了？太香了。你突破境界了。怎么都一个洋葱吧。一个味。你看。哦吼，哦吼，哦吼。 来口皇后 这果然是重庆的辣度了啊！我回。咋了？太香了。你突破境界了。怎么都一个洋葱吧。一个味。你看。好好。好好。但是，我感觉那个皇后更辣。刚才我又偷吃了一个，它油麻又辣。这皇后有很多的花椒啊，你看。来口皇后。 让我平常吃的多 怎么都一个洋葱吧？一个味儿。你看。哦好，哦好，哦好。但是我感觉那个黄喉更辣，刚才我又偷吃了一个，它油麻又辣。这黄喉有很多的花椒啊，你看。来口黄喉。哇，这黄喉咯吱咯吱的。巨嫩，很脆。 你像我平常吃的多的都是涮黄喉、烤黄喉。啊，对，很少吃火爆的。对。非常有锅气。 重庆的辣度真是提升了一 你像我平常吃的多都是涮黄喉、烤黄喉，啊，对，很少吃火爆的，对，非常有过去，嗯，爱了。这个黄喉我感觉就能干三碗饭。它这一份菜就可以下好多饭，它配菜都能吃。我感觉你脸都吃红了呢，有点。鼻子我辣。辣的。没有啊，我已经适应了。眼。 你知道为什没有啊，我已经适应了。演重庆的辣度真是提升了一个level啊。尝尝这土豆。还好藕丁没了。土豆脑袋狂洗。哎喝。土豆收割机。这喜欢吃土豆的人会爱铲子。你知道为什么吗？不知道，我还没吃呢。 这三 吃呢，那没偷着离我太远。它是那种炸过的，然后已经倍儿面了。哇，软软面面的，巨香无比，特别的辣。这个是味儿辣的。你说他会不会是炒一个锅底，然后里头加点不同的配菜，就出一锅啊？有可能吗？哇。这三个里边，土豆最棒。 如果不开车的话，哎，空中 最棒。我是翻译。他说他是岛民。超下饭。我们俩一盆饭吃就剩这么一点了。他也吃所剩无几了。一人吃了四碗。接下来我们要坐这个空中公交飞越长江啦。我们现在在南站。嗯。回到我们的解放碑。 都说北边 嗯，回到我们的解放碑。如果不开车的话，哎，空中的公交是非常好的选择呀，也是当地的交通工具呢。走了走了，先爬个坡坡。会会，哎，我们刚吃饱，就这么爬坡会阑尾炎吗？哈哈哈哈哈。重庆会打败每一个不喜欢运动的人。是的。",
        "candidate": "都说北边排队更久呢，南 的解放杯。如果不开车的话，哎，空中的公交是非常好的选择呀，也是当地的交通工具呢。走了走了，先爬个坡坡。会会，哎，我们刚吃饱，就这么爬坡会阑尾炎吗？哈哈哈哈哈。重庆会打败每一个不喜欢运动的人。是了。都说北边排队更久呢，南边人很少的。",
        "expected": "",
        "source": "2026-06-14 avc-whisper.log chunk 701 Chinese repeated route context",
    },
]


FINAL_QUALITY_TRACKING_CASES = [
    {"text": "潇洒最好的乳团。", "language": "zh", "expected_flags": {"short_cjk"}, "source": "2026-06-14 monitor chunk 421"},
    {"text": "蒸牛。", "language": "zh", "expected_flags": {"short_cjk"}, "source": "2026-06-14 monitor chunk 441"},
    {"text": "很漂亮的咖啡厅，而且。", "language": "zh", "expected_flags": {"short_cjk"}, "source": "2026-06-14 monitor chunk 537"},
    {"text": "Good oodbye.", "language": "zh", "expected_flags": {"latin_only_for_zh"}, "source": "2026-06-14 monitor chunk 504"},
    {"text": "Good morning.", "language": "zh", "expected_flags": {"latin_only_for_zh"}, "source": "2026-06-14 monitor chunk 506"},
    {"text": "Everybody should.", "language": "zh", "expected_flags": {"latin_only_for_zh"}, "source": "2026-06-14 avc-whisper.log.5 language-mismatch"},
    {"text": "As the mentionnearly.", "language": "zh", "expected_flags": {"latin_only_for_zh"}, "source": "2026-06-14 avc-whisper.log.5 language-mismatch"},
    {"text": "matcha ice cream很好吃。", "language": "zh", "expected_flags": {"mixed_latin_zh"}, "source": "synthetic zh mixed latin"},
    {"text": "Oh, my god,我真的很开心。", "language": "zh", "expected_flags": {"mixed_latin_zh"}, "source": "2026-06-14 avc-whisper.log.4 mixed latin zh"},
    {"text": "I love felelceline baby, baby, you oonly you, oh,你you can.", "language": "zh", "expected_flags": {"mixed_latin_zh"}, "source": "2026-06-14 avc-whisper.log.4 mixed latin zh"},
    {"text": "要 去 找", "language": "zh", "expected_flags": {"short_cjk", "no_end_marker"}, "source": "2026-06-14 monitor chunk 354"},
    {"text": "见 什 么 都 想 吃 这 可 怎 么 办 呀 我 看 见 大 闸 丸 了 人 刚 才 来 的 啊 肉 丸", "language": "zh", "expected_flags": {"no_end_marker", "spaced_cjk"}, "source": "2026-06-14 monitor chunk 723 spaced CJK output"},
    {"text": "一 看 到 这 东 西 直 抢 趁 着 我 这 几 天 还 能 吃 冰 了 我 赶 紧 吃", "language": "zh", "expected_flags": {"no_end_marker", "spaced_cjk"}, "source": "2026-06-15 Chinese monitor 20s chunk 113"},
    {"text": "我跟你说，就这一 得脱鞋！哇，它是楼梯好高啊。Hello，活动们，大家下午好。", "language": "zh", "expected_flags": {"mixed_latin_zh", "cjk_internal_gap"}, "source": "2026-06-14 monitor chunk 890 internal CJK gap"},
    {"text": "对，他的 了，中国人主打一来了，所以叫我进去走。", "language": "zh", "expected_flags": {"cjk_internal_gap"}, "source": "2026-06-14 monitor chunk 801 internal CJK gap"},
    {"text": "真的，吃这个干热午茶必须得是这半肥瘦，就是宽肉带皮的还 汤的，有油饭吗？", "language": "zh", "expected_flags": {"cjk_internal_gap"}, "source": "2026-06-14 avc-whisper.log.1 chunk 1817 internal gap"},
    {"text": "它是先做成一个寿司条，然后把这米再切断了，摆成四个墩墩，然后就是火山的底座，然后上面这个撒的就更像熔岩 他们这儿还有这个特殊菜单。", "language": "zh", "expected_flags": {"cjk_internal_gap"}, "source": "2026-06-15 avc-whisper.log chunk 3039 suppressed duplicate gap"},
    {
        "text": "招牌咖喱面，然后再喝一个阿玛胡药招牌咖喱面，然后再喝一个阿玛胡耀诗，石耀虎胡耀诗，米然后再喝一个阿玛胡耀诗，师耀虎胡耀诗，米粉餐面，两餐，好，我再给胡药师，师咬虎胡药师，米粉掺面，两餐，好，我再给你找一家吃的啊，咱现白老师，米粉掺面，两掺。好，我再给你找一家吃的啊。咱现在还差一家，现找。",
        "language": "zh",
        "expected_flags": {"cjk_repeated_ngram"},
        "source": "2026-06-15 10s Chinese monitor chunk 83 repeated CJK span",
    },
    {"text": "妈呀，隐形眼镜掉这午茶里了。又是没吃过的味道。嗯。", "language": "zh", "expected_flags": set(), "source": "2026-06-14 avc-whisper.log.1 chunk 1820 stable final"},
    {"text": "看起来好好吃啊，你真的有很多小吃呢，我看到。", "language": "zh", "expected_flags": set(), "source": "2026-06-14 monitor chunk 50 stable comparison"},
]


RUNTIME_METRIC_TRACKING_CASES = [
    {
        "metrics": {"candidate_duplicate_suppressed": 1, "completed_coalesced": 1},
        "expected": {"duplicate_suppressed": 1, "completed_coalesced": 1},
        "source": "2026-06-15 avc-whisper.log chunk 3039",
    },
    {
        "metrics": {"candidate_delta_trimmed": 1, "candidate_delta_trimmed_cjk": 1, "stage_start": 1},
        "expected": {"delta_trimmed": 1, "completed_coalesced": 0},
        "source": "2026-06-14 avc-whisper.log.1 chunk 1820",
    },
    {
        "metrics": {"final_quality_cjk_internal_gap": 1, "translation_skip_final_quality": 1},
        "expected": {"final_quality": 1, "translation_skip": 1},
        "source": "2026-06-14 translation skip quality diagnostic",
    },
    {
        "metrics": {"stage_revision": 1, "stage_revision_changed": 1, "stage_revision_confirmation_reset": 1},
        "expected": {"revision_changed": 1, "revision_reset": 1},
        "source": "2026-06-15 Chinese monitor CJK revision reset",
    },
    {
        "metrics": {"input_queue_drops": 5},
        "expected": {"input_queue_drops": 5},
        "source": "2026-06-15 30s/1s Chinese monitor Pulse queue saturation",
    },
    {
        "metrics": {"stage_candidate_released_reason_confirmed_quality_blocked": 1},
        "expected": {"quality_blocked_release": 1},
        "source": "2026-06-15 12s Chinese monitor confirmed quality block age overrun",
    },
]


class WhisperPerformanceTrackingTest(unittest.TestCase):
    records: list[tuple[str, str, bool]] = []

    @classmethod
    def tearDownClass(cls) -> None:
        by_domain: dict[str, list[bool]] = {}
        for domain, _name, matched in cls.records:
            by_domain.setdefault(domain, []).append(matched)

        parts = []
        for domain in sorted(TRACKING_TARGETS):
            target = TRACKING_TARGETS[domain]
            values = by_domain.get(domain, [])
            passed = sum(values)
            total = len(values)
            rate = passed / total if total else 0.0
            target_cases = int(target["target_cases"])
            target_rate = float(target["target_rate"])
            gap = max(0.0, target_rate - rate)
            case_gap = max(0, target_cases - total)
            parts.append(
                f"{domain}={passed}/{total} rate={rate:.3f} "
                f"target>={target_rate:.2f} cases_target>={target_cases} "
                f"rate_gap={gap:.3f} case_gap={case_gap}"
            )

        print("[whisper-tracking] " + " ".join(parts), file=sys.stderr)

    def _record(self, domain: str, name: str, matched: bool) -> None:
        self.records.append((domain, name, matched))


def _make_duplicate_suppression_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = _sentence_output_delta(str(case["committed"]), str(case["candidate"]))
        self._record("duplicate_suppression", f"duplicate_suppression_{index:03d}", actual == str(case["expected"]))
    return test


def _make_translation_quality_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        observed = str(case["observed"])
        required_any = set(case.get("required_any", set()))
        required_all = set(case.get("required_all", set()))
        forbidden_any = set(case.get("forbidden_any", set()))
        matched_any = any(term in observed for term in required_any) if required_any else True
        matched_all = all(term in observed for term in required_all)
        has_forbidden = any(term in observed for term in forbidden_any)
        matched = matched_any and matched_all and not has_forbidden
        self._record("translation_quality", f"translation_quality_{index:03d}", matched)
    return test


def _make_final_quality_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = set(_final_sentence_diagnostic_flags(str(case["text"]), str(case["language"])))
        expected = set(case["expected_flags"])
        matched = expected.issubset(actual) if expected else not actual
        self._record("final_quality", f"final_quality_{index:03d}", matched)
    return test

def _runtime_metric_summary(metrics: dict[str, int]) -> dict[str, int]:
    return {
        "duplicate_suppressed": int(metrics.get("candidate_duplicate_suppressed", 0)),
        "delta_trimmed": int(metrics.get("candidate_delta_trimmed", 0)),
        "final_quality": sum(value for key, value in metrics.items() if key.startswith("final_quality_")),
        "translation_skip": int(metrics.get("translation_skip_final_quality", 0)),
        "completed_coalesced": int(metrics.get("completed_coalesced", 0)),
        "revision_changed": int(metrics.get("stage_revision_changed", 0)),
        "revision_reset": int(metrics.get("stage_revision_confirmation_reset", 0)),
        "input_queue_drops": int(metrics.get("input_queue_drops", 0)),
        "quality_blocked_release": int(metrics.get("stage_candidate_released_reason_confirmed_quality_blocked", 0)),
    }


def _make_runtime_metric_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = _runtime_metric_summary({str(key): int(value) for key, value in dict(case["metrics"]).items()})
        expected = {str(key): int(value) for key, value in dict(case["expected"]).items()}
        matched = all(actual.get(key) == value for key, value in expected.items())
        self._record("runtime_metrics", f"runtime_metrics_{index:03d}", matched)
    return test


def _make_revision_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        left = str(case["left"])
        right = str(case["right"])
        matched = _sentences_are_revisions(left, right)
        delta = _sentence_output_delta(left, right)
        if delta == _normalized_text(right):
            matched = False
        self._record("revision", f"revision_{index:03d}", matched)
    return test


def _make_distinct_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        left = str(case["left"])
        right = str(case["right"])
        matched = not _sentences_are_revisions(left, right)
        self._record("distinct", f"distinct_{index:03d}", matched)
    return test


def _make_collapse_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        text = str(case["text"])
        collapsed, rules = _collapse_adjacent_repeated_phrase_details(text)
        matched = bool(rules) and len(_normalized_text(collapsed)) <= len(_normalized_text(text))
        self._record("collapse", f"collapse_{index:03d}", matched)
    return test


REVISION_TRACKING_CASES.extend([
    {
        "left": "我要的是一个四合一的大份十七，小份十六，还是非常丰 边的第一顿，必须得吃这个裤带面。你们看了吗？它超级的宽，因为它很像裤带，所以它叫裤带面。我要的是一个四合一的大份儿十七，小份儿十六，还是非常丰富的。",
        "right": "鸡蛋西红柿有剁椒，还有肉，还有土豆丁、胡萝卜丁，这儿 它很像裤带，所以它叫裤带面。我要的是一个四合一的大份儿十七，小份儿十六，还是非常丰富的。鸡蛋西红柿有剁椒，还有肉，还有土豆丁、胡萝卜丁，这儿还有点韭菜。",
        "source": "2026-06-14 avc-whisper.log chunks 48-49 Chinese window prefix reuse",
    },
    {
        "left": "韩国汤匙它是扁的，然后很长800块芝麻喔，它这个机器好酷喔，他们给我一点试吃。",
        "right": "它是扁的，然后很长800块芝麻，它这个机器好酷喔，他们给我一点试吃，它感觉有去炒过耶超香的。",
        "source": "2026-06-14 avc-whisper.log chunks 6-7 Chinese revised prefix before overlap",
    },
    {
        "left": "它这个膜很结实，它是用了西北秦川的黄牛肉来制作的，就是吃着不是很柴， 在我看来，那优质就是瘦一点，对吧？然后这普通就有点肥，你看里边那肥的，吃一口啊。这膜跟刚搬进膜是一个膜，大白膜。都叫脱脱膜，脱膜。 来 你看里边那肥的，吃一口啊。这馍跟刚搬进馍是一个馍。大白馍。都叫脱脱馍。脱馍。它这个馍很结实。它是用了西北秦川的黄牛肉来制作的，就是吃着不是很柴，吃着非常的嫩的那种牛肉。",
        "right": "它 馍跟刚拌进馍是一个馍，大白馍。都叫脱脱馍。脱馍。它这个馍很结实。它是用了西北秦川的黄牛肉来制作的，就是吃的不是很柴，吃的非常的嫩的那种牛肉。来了您的羊肉泡馍。谢谢。羊肉泡馍来了。哇，好香啊。",
        "source": "2026-06-14 avc-whisper.log chunk 10 Chinese committed tail block reuse",
    },
])


COALESCE_TRACKING_CASES = [
    {
        "language": "zh",
        "sentences": ["放了放一下吧，自己迷你韩美就是使劲夸夸，我们知道吗？", "魔法师你在吸我。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 121",
    },
    {
        "language": "zh",
        "sentences": ["使使夸夸我们，你知道吗？", "魔法师，你在吸我的氧气吗？"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 122",
    },
    {
        "language": "zh",
        "sentences": ["奎是什么？", "他说他不知道，我又不是。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 139",
    },
    {
        "language": "zh",
        "sentences": ["怎么啦？", "但餐厅的每一个角落真的很好看，尤其是中间划分出一个区域。", "中午的阳光透过玻璃洒进来，真。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 128",
    },
    {
        "language": "zh",
        "sentences": ["为什么不在九月？", "因为他八月手嘛，然后突破浪截真的有可能。", "哎，现在都十一月。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 158",
    },
    {
        "language": "zh",
        "sentences": ["Helps笨蛋，我们是笨蛋，你大家不笨蛋，它是芒果口味的。", "我一直以来你以为它是山楂。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 241",
    },
    {
        "language": "zh",
        "sentences": ["你大家不笨蛋，它是芒果口味的。", "我一直以来你以为它是山楂口味的，很好吃。", "哎，冰。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 242",
    },
    {
        "language": "zh",
        "sentences": ["唱的很高很高，是好朋友，你怎么容了？", "好朋友，我为什么还是这么猛烈？", "我们不是还要。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 251",
    },
    {
        "language": "zh",
        "sentences": ["怎么容了？", "好朋友，我为什么还是这么萌的呀？", "我们不是还要贴贴脸吗？", "你怎。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 252",
    },
    {
        "language": "zh",
        "sentences": ["果是怎么样？", "然后我让小哥哥给我拿了几台测试一下，就是室。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 269",
    },
    {
        "language": "zh",
        "sentences": ["果是怎么样？", "然后我让小哥哥给我拿了几台测试一下，就是室内室外光线不一样的。"],
        "expected_count": 1,
        "source": "avc-whisper.log chunk 270",
    },
    {
        "language": "zh",
        "sentences": ["他们都会就是跟你拿你的包包然。", "后给你换上相对应的。"],
        "expected_count": 1,
        "source": "avc-whisper.log.3 chunk 15722 unprocessed multi-completed zh",
    },
    {
        "language": "zh",
        "sentences": ["有一种莫名的熟悉感。", "第一次来韩国的时候是solo trip,去年是跟助理们一起来。"],
        "expected_count": 1,
        "source": "avc-whisper.log.3 chunk 15777 unprocessed mixed zh-latin multi-completed",
    },
    {
        "language": "ko",
        "sentences": ["첫 번째 문장입니다.", "두 번째 문장입니다."],
        "expected_count": 2,
        "source": "non-zh control",
    },
]


def _make_coalesce_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        sentences = [str(item) for item in case["sentences"]]
        actual = _coalesce_completed_sentences_for_staging(sentences, str(case["language"]))
        matched = len(actual) == int(case["expected_count"])
        self._record("coalesce", f"coalesce_{index:03d}", matched)
    return test


def _make_pending_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = _pending_overrun_reason(str(case["pending"]), int(case["chunks"]))
        matched = actual == str(case["expected"])
        self._record("pending", f"pending_{index:03d}", matched)
    return test


def _make_pending_quality_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = set(
            _pending_text_diagnostic_flags(
                str(case["pending"]),
                str(case["language"]),
                int(case["chunks"]),
            )
        )
        expected = set(case["expected_flags"])
        matched = expected.issubset(actual)
        self._record("pending_quality", f"pending_quality_{index:03d}", matched)
    return test


def _make_replacement_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        actual = _replacement_decision_reason(
            str(case["staged"]),
            str(case["candidate"]),
            int(case.get("confirmations", 1)),
            bool(case.get("forced", False)),
            int(case.get("age", 0)),
        )
        matched = actual == str(case["expected"])
        self._record("replacement", f"replacement_{index:03d}", matched)
    return test


def _make_stage_candidate_tracking_test(index: int, case: dict[str, object]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        reason = _replacement_decision_reason(
            str(case["staged"]),
            str(case["candidate"]),
            int(case.get("confirmations", 1)),
            bool(case.get("forced", False)),
            int(case.get("age", 0)),
        )
        actual = _should_stage_replacement_candidate(
            str(case["staged"]),
            str(case["candidate"]),
            reason,
            int(case.get("age", 0)),
            int(case.get("max_age", 3)),
        )
        self._record("stage_candidate", f"stage_candidate_{index:03d}", actual == bool(case["expected"]))
    return test


def _make_stability_tracking_test(index: int, sequence: list[str]):
    def test(self: WhisperPerformanceTrackingTest) -> None:
        transition_results = []
        for left, right in zip(sequence, sequence[1:]):
            is_revision = _sentences_are_revisions(left, right)
            full_reemit = _sentence_output_delta(left, right) == _normalized_text(right)
            transition_results.append(is_revision and not full_reemit)
        matched = bool(transition_results) and (sum(transition_results) / len(transition_results)) >= 0.80
        self._record("stability", f"stability_{index:03d}", matched)
    return test


for _index, _case in enumerate(COALESCE_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_coalesce_{_index:03d}",
        _make_coalesce_tracking_test(_index, _case),
    )


for _index, _case in enumerate(DUPLICATE_SUPPRESSION_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_duplicate_suppression_{_index:03d}",
        _make_duplicate_suppression_tracking_test(_index, _case),
    )


for _index, _case in enumerate(TRANSLATION_OBSERVED_QUALITY_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_translation_quality_{_index:03d}",
        _make_translation_quality_tracking_test(_index, _case),
    )

for _index, _case in enumerate(FINAL_QUALITY_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_final_quality_{_index:03d}",
        _make_final_quality_tracking_test(_index, _case),
    )

for _index, _case in enumerate(RUNTIME_METRIC_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_runtime_metrics_{_index:03d}",
        _make_runtime_metric_tracking_test(_index, _case),
    )

for _index, _case in enumerate(PENDING_QUALITY_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_pending_quality_{_index:03d}",
        _make_pending_quality_tracking_test(_index, _case),
    )

for _index, _case in enumerate(REVISION_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_revision_{_index:03d}",
        _make_revision_tracking_test(_index, _case),
    )

for _index, _case in enumerate(DISTINCT_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_distinct_{_index:03d}",
        _make_distinct_tracking_test(_index, _case),
    )

for _index, _case in enumerate(COLLAPSE_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_collapse_{_index:03d}",
        _make_collapse_tracking_test(_index, _case),
    )


for _index, _case in enumerate(PENDING_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_pending_{_index:03d}",
        _make_pending_tracking_test(_index, _case),
    )

for _index, _case in enumerate(REPLACEMENT_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_replacement_{_index:03d}",
        _make_replacement_tracking_test(_index, _case),
    )

for _index, _case in enumerate(STAGE_CANDIDATE_TRACKING_CASES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_stage_candidate_{_index:03d}",
        _make_stage_candidate_tracking_test(_index, _case),
    )

for _index, _sequence in enumerate(STABILITY_TRACKING_SEQUENCES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_stability_{_index:03d}",
        _make_stability_tracking_test(_index, _sequence),
    )



if __name__ == "__main__":
    unittest.main()
