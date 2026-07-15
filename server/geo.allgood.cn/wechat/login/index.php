<?php
http_response_code(302);
header('Location: /login/?wechat_disabled=1');
exit;
