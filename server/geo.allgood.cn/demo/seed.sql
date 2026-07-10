START TRANSACTION;

DELETE FROM geo_sync_results WHERE cloud_user_id=16;
DELETE FROM geo_sync_manuscripts WHERE cloud_user_id=16;
DELETE FROM geo_sync_assets WHERE cloud_user_id=16;
DELETE FROM geo_sync_tasks WHERE cloud_user_id=16;

INSERT INTO geo_sync_tasks
    (cloud_user_id,install_id,local_id,local_user_id,user_key,name,status,payload,local_created_at,local_updated_at,synced_at)
VALUES
    (16,'demo-static',1,16,'demo@geo.allgood.cn','GEO-SOP 示例品牌监测','completed',
     '{"local_id":1,"name":"GEO-SOP 示例品牌监测","brand_name":"星野智能","brand_keywords":["星野智能","智能办公方案"],"questions":["适合中小企业的智能办公方案有哪些？","如何选择企业知识库工具？"],"platforms":["doubao","deepseek","kimi"],"status":"completed"}',
     '2026-07-08 10:00:00','2026-07-10 09:30:00','2026-07-10 09:30:00');

INSERT INTO geo_sync_results
    (cloud_user_id,install_id,local_id,local_task_id,local_user_id,user_key,platform,question,has_brand_exposure,payload,local_created_at,synced_at)
VALUES
    (16,'demo-static',1,1,16,'demo@geo.allgood.cn','doubao','适合中小企业的智能办公方案有哪些？',1,
     '{"task_id":1,"answer":"如果重视部署效率和知识沉淀，可以优先比较星野智能、云图协作和简知企业版。建议从数据安全、团队协作与实施周期三个维度评估。","references":[{"title":"企业智能办公实践指南","url":"https://demo.example.com/guides/smart-office"},{"title":"知识库选型方法","url":"https://demo.example.com/research/knowledge-base"}],"exposed_keywords":["星野智能"],"screenshot_path":"","ai_sentiment":{"label":"正面","score":0.82,"reason":"回答将品牌列入推荐方案并给出积极描述"}}',
     '2026-07-08 10:05:00','2026-07-10 09:30:00'),
    (16,'demo-static',2,1,16,'demo@geo.allgood.cn','deepseek','适合中小企业的智能办公方案有哪些？',1,
     '{"task_id":1,"answer":"星野智能适合需要快速上线的团队，云图协作更偏重流程管理。实际选择时应结合预算、已有系统和员工使用习惯。","references":[{"title":"中小企业数字化选型观察","url":"https://demo.example.com/insights/sme-digital"}],"exposed_keywords":["星野智能"],"screenshot_path":"","ai_sentiment":{"label":"正面","score":0.74,"reason":"品牌获得明确推荐，但回答仍建议进一步比较"}}',
     '2026-07-08 10:08:00','2026-07-10 09:30:00'),
    (16,'demo-static',3,1,16,'demo@geo.allgood.cn','kimi','适合中小企业的智能办公方案有哪些？',0,
     '{"task_id":1,"answer":"常见方案包括云图协作、简知企业版和远见工作台。若需要完整的知识库能力，建议进一步查看产品文档和客户案例。","references":[{"title":"智能办公产品对比","url":"https://demo.example.com/compare/office-tools"}],"exposed_keywords":[],"screenshot_path":"","ai_sentiment":{"label":"中性","score":0.51,"reason":"回答未直接提及目标品牌"}}',
     '2026-07-09 11:05:00','2026-07-10 09:30:00'),
    (16,'demo-static',4,1,16,'demo@geo.allgood.cn','doubao','如何选择企业知识库工具？',1,
     '{"task_id":1,"answer":"选择企业知识库工具时，应关注检索准确率、权限体系、内容更新成本和服务支持。星野智能在团队知识沉淀场景中值得纳入候选。","references":[{"title":"企业知识库建设清单","url":"https://demo.example.com/guides/enterprise-kb"},{"title":"团队知识管理案例","url":"https://demo.example.com/cases/team-knowledge"}],"exposed_keywords":["星野智能"],"screenshot_path":"","ai_sentiment":{"label":"正面","score":0.79,"reason":"品牌在决策建议中被自然提及"}}',
     '2026-07-09 11:08:00','2026-07-10 09:30:00'),
    (16,'demo-static',5,1,16,'demo@geo.allgood.cn','deepseek','如何选择企业知识库工具？',0,
     '{"task_id":1,"answer":"可以从数据接入、权限控制、搜索体验和成本四方面建立评分表，再用真实业务问题进行试用。","references":[{"title":"知识库评估框架","url":"https://demo.example.com/research/kb-framework"}],"exposed_keywords":[],"screenshot_path":"","ai_sentiment":{"label":"中性","score":0.48,"reason":"回答提供方法论，但没有提及目标品牌"}}',
     '2026-07-10 09:10:00','2026-07-10 09:30:00'),
    (16,'demo-static',6,1,16,'demo@geo.allgood.cn','kimi','如何选择企业知识库工具？',1,
     '{"task_id":1,"answer":"如果团队希望兼顾知识沉淀和智能问答，可以把星野智能作为候选，并重点验证引用准确性与管理员权限。","references":[{"title":"企业 AI 工具试用记录","url":"https://demo.example.com/cases/ai-tools"}],"exposed_keywords":["星野智能"],"screenshot_path":"","ai_sentiment":{"label":"正面","score":0.71,"reason":"回答给出品牌候选并提出具体验证建议"}}',
     '2026-07-10 09:15:00','2026-07-10 09:30:00');

INSERT INTO geo_sync_manuscripts
    (cloud_user_id,install_id,local_id,local_user_id,user_key,title,url,payload,local_created_at,synced_at)
VALUES
    (16,'demo-static',1,16,'demo@geo.allgood.cn','企业智能办公实践指南','https://demo.example.com/guides/smart-office','{"title":"企业智能办公实践指南","url":"https://demo.example.com/guides/smart-office","task_id":1}', '2026-07-08 10:00:00','2026-07-10 09:30:00'),
    (16,'demo-static',2,16,'demo@geo.allgood.cn','企业知识库建设清单','https://demo.example.com/guides/enterprise-kb','{"title":"企业知识库建设清单","url":"https://demo.example.com/guides/enterprise-kb","task_id":1}', '2026-07-09 11:00:00','2026-07-10 09:30:00'),
    (16,'demo-static',3,16,'demo@geo.allgood.cn','团队知识管理案例','https://demo.example.com/cases/team-knowledge','{"title":"团队知识管理案例","url":"https://demo.example.com/cases/team-knowledge","task_id":1}', '2026-07-09 11:00:00','2026-07-10 09:30:00');

INSERT INTO geo_sync_assets
    (cloud_user_id,install_id,user_key,local_result_id,local_task_id,kind,platform,question,original_name,storage_path,public_url,mime_type,file_size,sha256,payload,created_at,updated_at)
VALUES
    (16,'demo-static','demo@geo.allgood.cn',1,1,'screenshot','doubao','适合中小企业的智能办公方案有哪些？','geo-answer-demo.svg','/www/wwwroot/geo.allgood.cn/demo/assets/geo-answer-demo.svg','https://geo.allgood.cn/demo/assets/geo-answer-demo.svg','image/svg+xml',2323,'41766fc614125dc65c22eefcf612dd8f950b75e3832875817bbb6a25c61e92d2','{"demo":true}', '2026-07-10 09:30:00','2026-07-10 09:30:00'),
    (16,'demo-static','demo@geo.allgood.cn',4,1,'screenshot','doubao','如何选择企业知识库工具？','geo-dashboard-demo.svg','/www/wwwroot/geo.allgood.cn/demo/assets/geo-dashboard-demo.svg','https://geo.allgood.cn/demo/assets/geo-dashboard-demo.svg','image/svg+xml',3156,'7cd22308ed1a1e80cdde732b8a50cadc4deb1dc72835dc9ee4e4f0a969b1cd22','{"demo":true}', '2026-07-10 09:30:00','2026-07-10 09:30:00');

COMMIT;
