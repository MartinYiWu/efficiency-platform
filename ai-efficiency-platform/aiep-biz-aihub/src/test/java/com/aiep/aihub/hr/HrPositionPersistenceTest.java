package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import com.aiep.aihub.repository.hr.HrPositionMapper;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Set;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.*;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.Test;

class HrPositionPersistenceTest {
    @Test void sequence_filtered_scope_and_draft_cas_use_real_sql() throws Exception {
        var ds=new JdbcDataSource();ds.setURL("jdbc:h2:mem:position_"+System.nanoTime()+";MODE=MySQL;DB_CLOSE_DELAY=-1");
        try(var c=ds.getConnection();var st=c.createStatement()) {
            for(String sql:Files.readString(Path.of("../sql/migration/V1.2.0__hr_positions_candidates_and_matching.sql")).split(";"))if(!sql.isBlank())st.execute(sql);
        }
        var config=new Configuration(new Environment("test",new JdbcTransactionFactory(),ds));config.setMapUnderscoreToCamelCase(true);config.addMapper(HrPositionMapper.class);
        try(InputStream xml=Files.newInputStream(Path.of("src/main/resources/mapper/hr/HrPositionMapper.xml"))){new XMLMapperBuilder(xml,config,"hr-position",config.getSqlFragments()).parse();}
        try(SqlSession session=new SqlSessionFactoryBuilder().build(config).openSession(true)){
            var mapper=session.getMapper(HrPositionMapper.class);
            mapper.allocateCode("t","d");assertEquals(1,mapper.currentCode("t","d"));mapper.allocateCode("t","d");assertEquals(2,mapper.currentCode("t","d"));
            mapper.insert(new HrPositionMapper.PositionRow("p","t","后端","后端","TECHNOLOGY","d","P6","d-000001","DRAFT",null,"ctx-1","1",Instant.now(),1));
            assertEquals(1,mapper.count("t",Set.of("d"),null,"TECHNOLOGY","DRAFT"));
            assertEquals(0,mapper.count("t",Set.of("other"),null,null,null));
            assertEquals(0,mapper.count("t",Set.of("d"),null,null,"ACTIVE"));
            assertEquals(1,mapper.advanceDraft("t","p",1));assertEquals(0,mapper.advanceDraft("t","p",1));
            mapper.writeDraft("t","p","{\"test\":true}",2);assertEquals(2,mapper.draft("t","p").version());
        }
    }
}
