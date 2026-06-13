import sys
import unittest

from src.app.whisper_window import (
    _collapse_adjacent_repeated_phrase_details,
    _normalized_text,
    _sentence_output_delta,
    _sentences_are_revisions,
)


# These service-gate cases are mined from accumulated .tmp/logs/avc-whisper.log* files.
# The thresholds below are service criteria, not implementation-fit targets. If a gate fails,
# improve the transcript revision/collapse behavior or add representative cases; do not loosen
# the thresholds to match the current code.
SERVICE_PASS_CRITERIA = {
    "revision": {"min_cases": 90, "min_rate": 0.90},
    "distinct": {"min_cases": 25, "min_rate": 0.95},
    "collapse": {"min_cases": 45, "min_rate": 0.90},
    "stability": {"min_cases": 10, "min_rate": 0.80},
}

REVISION_TRACKING_CASES = [{'left': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는',
  'ratio': 0.974,
  'right': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전',
  'source': 'avc-whisper.log'},
 {'left': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전',
  'ratio': 0.918,
  'right': '이자 비용 줄어들면서 얘는 자동적으로 또 떨어지는 시스템이 구축이 된다는 거죠 지금과는 완전 반대의 사이클로',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠', 'ratio': 0.744, 'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서', 'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서',
  'ratio': 0.806,
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리',
  'ratio': 0.879,
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도',
  'source': 'avc-whisper.log'},
 {'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도',
  'ratio': 0.981,
  'right': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도 굳이',
  'source': 'avc-whisper.log'},
 {'left': '재정적 프리미엄이', 'ratio': 0.889, 'right': '재정적 프리미엄이 과거', 'source': 'avc-whisper.log'},
 {'left': '재정적 프리미엄이 과거', 'ratio': 0.69, 'right': '재정적 프리미엄이 과거 수준으로 돌아가면서', 'source': 'avc-whisper.log'},
 {'left': '있었던 기간 프리미엄의 마이너스', 'ratio': 0.903, 'right': '있었던 기간 프리미엄의 마이너스 영역이', 'source': 'avc-whisper.log'},
 {'left': '복귀가 되면서 미국', 'ratio': 0.667, 'right': '복귀가 되면서 미국 국채금리는 떨어질', 'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오', 'ratio': 0.8, 'right': '그래서 그 시나리오 대로라면', 'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오 대로라면', 'ratio': 0.667, 'right': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은', 'ratio': 0.812, 'right': '실제로 올해랑 작년에 한국 같은 케이스에서도', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도', 'ratio': 0.792, 'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의',
  'ratio': 0.951,
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세',
  'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정',
  'ratio': 0.937,
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의',
  'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의',
  'ratio': 0.944,
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정 부분 정부의 구조 자체를',
  'source': 'avc-whisper.log'},
 {'left': '바꾸는 모습들로', 'ratio': 0.7, 'right': '바꾸는 모습들로 가져왔잖아요.', 'source': 'avc-whisper.log'},
 {'left': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는', 'ratio': 0.65, 'right': '바꾸는 모습들로 가져왔잖아요.', 'source': 'avc-whisper.log'},
 {'left': '바꾸는 모습들로 가져왔잖아요.', 'ratio': 0.605, 'right': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는 결국에.', 'source': 'avc-whisper.log'},
 {'left': '그런데 그 구조 자체를 바꾸는 모습들로 가져왔잖아요 근데 문제는 결국에.', 'ratio': 0.421, 'right': '근데 문제는 결국에.', 'source': 'avc-whisper.log'},
 {'left': '세수가 많이 들어오면 정부가 할 수 있는', 'ratio': 0.842, 'right': '세수가 많이 들어오면 정부가 할 수 있는 건 두 가지예요.', 'source': 'avc-whisper.log'},
 {'left': '세수가 많이 들어오면 정부가 할 수 있는 건 두 가지예요.', 'ratio': 0.878, 'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지', 'source': 'avc-whisper.log'},
 {'left': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지', 'ratio': 0.884, 'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는', 'source': 'avc-whisper.log'},
 {'left': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는',
  'ratio': 0.923,
  'right': '추가 많이 들어오면 정부가 할 수 있는 건 두 가지 첫 번째로는 가지예요.',
  'source': 'avc-whisper.log'},
 {'left': '빚을 갚는다 빚을 줄인다 두', 'ratio': 0.71, 'right': '빚을 갚는다 빚을 줄인다 두 번째는 아니야 투자를', 'source': 'avc-whisper.log'},
 {'left': '빚을 갚는다 빚을 줄인다 두 번째는 아니야 투자를 한다.', 'ratio': 0.872, 'right': '빚을 줄인다 두 번째는 아니야 투자를 한다', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인', 'ratio': 0.867, 'right': '투자를 하면 성장을 하는 요인인 거고 빚을', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을', 'ratio': 0.919, 'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면', 'ratio': 0.833, 'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는', 'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는',
  'ratio': 0.918,
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두',
  'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두',
  'ratio': 0.868,
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고',
  'source': 'avc-whisper.log'},
 {'left': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고',
  'ratio': 0.915,
  'right': '투자를 하면 성장을 하는 요인인 거고 빚을 갚으면 재정을 개선시키는 거예요 뭐 두 가지 섞어서 할 수도 있고 한쪽에 몰빵할 수도',
  'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국', 'ratio': 0.889, 'right': '있는 건데 지금 한국 같은', 'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국 같은', 'ratio': 0.87, 'right': '있는 건데 지금 한국 같은 경우는.', 'source': 'avc-whisper.log'},
 {'left': '투자를 하겠다.', 'ratio': 0.8, 'right': '경우는 투자를 하겠다.', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는', 'ratio': 0.609, 'right': '미국 같은 경우는 일단은 빛은 연준보고', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고', 'ratio': 0.744, 'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할', 'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할',
  'ratio': 0.9,
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 안',
  'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 안',
  'ratio': 0.835,
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을',
  'source': 'avc-whisper.log'},
 {'left': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을',
  'ratio': 0.902,
  'right': '미국 같은 경우는 일단은 빛은 연준보고 빚은 연준보고 갚으라고 할 건데 연준이 할건데 연준이 안해준다면 반반을 해준다면 반반을 하겠죠',
  'source': 'avc-whisper.log'},
 {'left': '투자도 하고 빚도 갚고 뭐 이런', 'ratio': 0.774, 'right': '투자도 하고 빚도 갚고 뭐 이런 식으로 나누는 게', 'source': 'avc-whisper.log'},
 {'left': '지금 정부가 이제 기업들의', 'ratio': 0.579, 'right': '지금 정부가 이제 기업들의 정부가 기업들의 세수가 들어왔을 때 할', 'source': 'avc-whisper.log'},
 {'left': '것 같아요 그러면 지금 ai 산업에는', 'ratio': 0.833, 'right': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더', 'source': 'avc-whisper.log'},
 {'left': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더',
  'ratio': 0.824,
  'right': '것 같아요 그러면 지금 ai 산업에는 여전히 조금 더 계속 지속적인 투자가',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인', 'ratio': 0.842, 'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두', 'ratio': 0.936, 'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로',
  'ratio': 0.862,
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를',
  'ratio': 0.971,
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고',
  'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고',
  'ratio': 0.946,
  'right': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고 있는 국가',
  'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서', 'ratio': 0.533, 'right': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을', 'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을', 'ratio': 0.88, 'right': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을 하고 있잖아요.', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야', 'ratio': 0.311, 'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고',
  'ratio': 0.8,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이',
  'ratio': 0.942,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을',
  'ratio': 0.928,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데',
  'ratio': 0.98,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일',
  'ratio': 0.969,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를',
  'ratio': 0.959,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서',
  'ratio': 0.86,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을',
  'ratio': 0.979,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을 투자를 하고',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 1등의 자리를 고수하기 위해서 결국에 미국은 계속적으로 투쟁을 투자를 하고',
  'ratio': 0.921,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고',
  'ratio': 0.971,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에',
  'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에',
  'ratio': 0.972,
  'right': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 '
           '위해서 그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에 들어오라고 하고',
  'source': 'avc-whisper.log'},
 {'left': '이런 생태를 할 수밖에', 'ratio': 0.9, 'right': '이런 생태를 할 수밖에 없는', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속', 'ratio': 0.929, 'right': '그런데 연준 쪽에서 금리를 계속 거죠', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 거죠', 'ratio': 0.846, 'right': '그런데 연준 쪽에서 금리를', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를', 'ratio': 0.688, 'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을', 'ratio': 0.808, 'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금',
  'ratio': 0.925,
  'right': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금 이제 버거워',
  'source': 'avc-whisper.log'},
 {'left': '버거워지잖아요 트럼프', 'ratio': 0.625, 'right': '버거워지잖아요 트럼프 받기가 조금 버거워지잖아요.', 'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의', 'ratio': 0.577, 'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런', 'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런',
  'ratio': 0.771,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기',
  'ratio': 0.944,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의',
  'ratio': 0.943,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을',
  'ratio': 0.961,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는',
  'ratio': 0.97,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 세상에서는 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고',
  'ratio': 0.866,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게',
  'ratio': 0.969,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을',
  'source': 'avc-whisper.log'},
 {'left': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을',
  'ratio': 0.994,
  'right': '트럼프 입장에서는 기업들 단에서의 맞아요 트럼프 입장에서는 이제 기업들 딴에서의 그런 힘겨움을 끌어주기 위해서 트럼프의 정책적 방향성들을 제시할 수 있는 거고 그리고 이제 만약에 그렇게 투자를 했을 때',
  'source': 'avc-whisper.log'},
 {'left': '기업들로 돌아가는 이익이라든지 이런', 'ratio': 0.842, 'right': '기업들로 돌아가는 이익이라든지 이런 부분들에 대한', 'source': 'avc-whisper.log'},
 {'left': '제도적 개선들을 만들어낼', 'ratio': 0.71, 'right': '제도적 개선들을 만들어낼 수 있는 부분들도 있을', 'source': 'avc-whisper.log'},
 {'left': '그걸 과거에는 연준이', 'ratio': 0.5, 'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데', 'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데',
  'ratio': 0.818,
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의',
  'ratio': 0.975,
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할',
  'ratio': 0.872,
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고',
  'ratio': 0.981,
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는',
  'source': 'avc-whisper.log'},
 {'left': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는',
  'ratio': 0.965,
  'right': '부분들도 있을 것 같아요 그걸 과거에는 연준이 했었죠 그렇죠 근데 그런데 지금 이부터는 연준의 역할 자체는 아무것도 안 하겠다고 하는 거잖아요.',
  'source': 'avc-whisper.log'},
 {'left': '그럼 결국에는 재정의 역할이 커질 수밖에', 'ratio': 0.773, 'right': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는', 'source': 'avc-whisper.log'},
 {'left': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는',
  'ratio': 0.931,
  'right': '그럼 결국에는 재정의 역할이 커질 수밖에 없는 거고 커져야만 하는 상황이고',
  'source': 'avc-whisper.log'}]

DISTINCT_TRACKING_CASES = [{'left': '그렇게 됐을 경우는 금리가 떨어지겠죠 그러면 경기부가 버티면서 경기부와 버티면서 연준은 금리 그러면 인하를 하지 않아도 굳이',
  'ratio': 0.066,
  'right': '재정적 프리미엄이',
  'source': 'avc-whisper.log'},
 {'left': '있었던 기간 프리미엄의 마이너스 영역이', 'ratio': 0.08, 'right': '복귀가 되면서 미국', 'source': 'avc-whisper.log'},
 {'left': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세',
  'ratio': 0.071,
  'right': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.',
  'source': 'avc-whisper.log'},
 {'left': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.',
  'ratio': 0.033,
  'right': '실제로 올해랑 작년에 한국 같은 케이스에서도 삼성전자랑 하이너스의 법인세 세수가 일정',
  'source': 'avc-whisper.log'},
 {'left': '있는 건데 지금 한국 같은 경우는.', 'ratio': 0.0, 'right': '투자를 하겠다.', 'source': 'avc-whisper.log'},
 {'left': '수 있는 행태라고 보시면 되실', 'ratio': 0.074, 'right': '것 같아요 그러면 지금 ai 산업에는', 'source': 'avc-whisper.log'},
 {'left': '이제는 멈출 수가 없는 산업의 사이클인 거죠 그리고 두 번째로 미국이 가장 경계를 하고 있는 국가', 'ratio': 0.043, 'right': '중국 AI 관련돼서', 'source': 'avc-whisper.log'},
 {'left': '중국 AI 관련돼서 AI에 관련돼서 지금 패권전쟁을 하고 있잖아요.', 'ratio': 0.0, 'right': '내가 1등 할 거야', 'source': 'avc-whisper.log'},
 {'left': '내가 1등 할 거야 관련돼서 지금 패권 전쟁을 하고 있잖아요 내가 일 등 할 거야 라고 지금 달리고 거야라고 지금 달리고 있고 이제 삼 등을 한국이 있고 이제 3등을 할 거야라고 하고 있는데 그럼 일 등의 자리를 고수하기 위해서 '
          '그럼 결국에 미국은 계속적으로 투쟁을 투자를 하고 산업을 살리고 쏟고 글로벌단에 들어오라고 하고',
  'ratio': 0.043,
  'right': '이런 생태를 할 수밖에',
  'source': 'avc-whisper.log'},
 {'left': '이런 생태를 할 수밖에 없는', 'ratio': 0.167, 'right': '그런데 연준 쪽에서 금리를 계속', 'source': 'avc-whisper.log'},
 {'left': '그런데 연준 쪽에서 금리를 계속 올려버리면 대출을 이제 대출을 받기가 조금 이제 버거워', 'ratio': 0.13, 'right': '버거워지잖아요 트럼프', 'source': 'avc-whisper.log'},
 {'left': '기업들로 돌아가는 이익이라든지 이런 부분들에 대한', 'ratio': 0.121, 'right': '제도적 개선들을 만들어낼', 'source': 'avc-whisper.log'},
 {'left': '볼 수 있는 시나리오 그럼 이게 딱히 뭐 그렇게 절망적으로 볼 상황은 근데 모르겠어요 어디까지나 이제 그런데 모르겠어요.',
  'ratio': 0.19,
  'right': '어디까지나 이론적인 부분인 거고',
  'source': 'avc-whisper.log'},
 {'left': '그러면서 시장금리 이렇게 흘러내렸던 게 일반적이었는데 왜냐하면 레버리지 구조의 경계 구조기',
  'ratio': 0.2,
  'right': '망가졌었고 연준이 나서서 얘를 구해줬었어요 그러면서 시장 구해줬어요.',
  'source': 'avc-whisper.log'},
 {'left': '망가졌었고 연준이 나서서 얘를 구해줬었어요 그러면서 시장 구해줬어요.',
  'ratio': 0.182,
  'right': '그러면서 시장금리 이렇게 흘러내렸던 게 일반적이었는데 왜냐하면 레버리지 구조의 경계 구조기 구조이기 때문에',
  'source': 'avc-whisper.log'},
 {'left': '높은 거예요 그래서 버티고 가자 쪽으로 가는 거니까 금리가 높아도 이쪽으로 돈이 계속 들어가다', 'ratio': 0.125, 'right': '보니까 경기가 버티고', 'source': 'avc-whisper.log'},
 {'left': '이거는 위기가 나와봐야 하지 나와 봐야지 않은 거고 이거는 위기가 나와봐야지 아는 거고 너무 많이 바뀌고 이제 바뀌고 있는 산업의 경로기',
  'ratio': 0.032,
  'right': '때문에 돌아갈지',
  'source': 'avc-whisper.log'},
 {'left': '돈은 낮은 쪽에서 높은 쪽으로 쏠릴 수밖에 없어요 그리고 한국은행이 올해 금리 올린다고 하잖아요.', 'ratio': 0.042, 'right': '근데 문제는 아무리', 'source': 'avc-whisper.log'},
 {'left': '그러면 원달러 원달러안율은 지금 1500원대 환율은 지금 1500원대 너무 높아 보이는데 이게 어느 순간 뉴노멀로 인식이 되고 1500원이 아니라 1600원',
  'ratio': 0.123,
  'right': '1700원으로도 얼마든지 갈',
  'source': 'avc-whisper.log'},
 {'left': '1700원으로도 얼마든지 갈 수 천육백 원 천칠백 있는 내러티비를 만들어낼 수 내로티비를 만들어 낼 수 있다는 거죠.',
  'ratio': 0.0,
  'right': '그래서 제가 최근에',
  'source': 'avc-whisper.log'},
 {'left': '그래서 제가 최근에 이제 가장 많이 받던 질문 봤던 질문 중 중 하나는 다시 뭐 예전에 우리 1300원 1200원 천삼백 원 천이백 원 이게 좀',
  'ratio': 0.032,
  'right': '일반적이지 않냐',
  'source': 'avc-whisper.log'},
 {'left': '비상식적이다 결국에 낮아질까 낮아질 수 있겠지 이런 기대감들은 조금 있어요 근데 제가 말씀드리고 싶은 건',
  'ratio': 0.111,
  'right': '이전에 경험해보지 못한',
  'source': 'avc-whisper.log'},
 {'left': '예전에 베이스 레벨이 1200원대가 베이스였다면 지금은 베이스 레벨이 천이백 원대가 베이스였다면 지금은 천오백 원대 1500원대 플러스 알파가 베이스 레벨일 수도 있겠다 라는 있겠다라는 생각이 있겠다는 생각이 채권 시장 있을 '
          '레벨일 수도 있겠다는 생각이 채권시장 정치적인 관계 정치적인 관계 그리고 이제 통화 정책 관계',
  'ratio': 0.083,
  'right': '통화정책 관계 정부의',
  'source': 'avc-whisper.log'},
 {'left': '정부의 관계 이런 모든 투자 사이클이라든지 이런 부분들에서 다 나타나고 있다는', 'ratio': 0.227, 'right': '통화정책 관계 정부의 관계', 'source': 'avc-whisper.log'},
 {'left': '통화정책 관계 정부의 관계',
  'ratio': 0.182,
  'right': '정부의 관계 이런 모든 투자 사이클이라든지 이런 부분들에서 다 나타나고 있다는 왜냐하면 연준은 금리 이상',
  'source': 'avc-whisper.log'}]

COLLAPSE_TRACKING_CASES = [{'source': 'avc-whisper.log', 'text': '그래서 그 시나리오 대로라면 그래서 그 시나리오대로라면.'},
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


class WhisperPerformanceTrackingTest(unittest.TestCase):
    records: list[tuple[str, str, bool]] = []

    @classmethod
    def tearDownClass(cls) -> None:
        by_domain: dict[str, list[bool]] = {}
        for domain, _name, matched in cls.records:
            by_domain.setdefault(domain, []).append(matched)

        parts = []
        failures = []
        for domain in sorted(SERVICE_PASS_CRITERIA):
            criteria = SERVICE_PASS_CRITERIA[domain]
            values = by_domain.get(domain, [])
            passed = sum(values)
            total = len(values)
            rate = passed / total if total else 0.0
            min_cases = int(criteria["min_cases"])
            min_rate = float(criteria["min_rate"])
            parts.append(
                f"{domain}={passed}/{total} rate={rate:.3f} "
                f"gate>={min_rate:.2f} cases>={min_cases}"
            )
            if total < min_cases:
                failures.append(f"{domain}: cases {total} < {min_cases}")
            if rate < min_rate:
                failures.append(f"{domain}: rate {rate:.3f} < {min_rate:.2f}")

        print("[whisper-tracking] " + " ".join(parts), file=sys.stderr)
        if failures:
            raise AssertionError("Whisper service pass criteria failed: " + "; ".join(failures))

    def _record(self, domain: str, name: str, matched: bool) -> None:
        self.records.append((domain, name, matched))


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

for _index, _sequence in enumerate(STABILITY_TRACKING_SEQUENCES, 1):
    setattr(
        WhisperPerformanceTrackingTest,
        f"test_tracking_stability_{_index:03d}",
        _make_stability_tracking_test(_index, _sequence),
    )



if __name__ == "__main__":
    unittest.main()
